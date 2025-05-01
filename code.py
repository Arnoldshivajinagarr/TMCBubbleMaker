import os
import logging
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import pandas as pd
from sqlalchemy import Enum
import enum

# --- Configuration ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'outputs')
ALLOWED_EXTENSIONS = {'csv', 'txt'}

# --- App Initialization ---
app = Flask(__name__)
# IMPORTANT: Change this secret key in a real application!
app.config['SECRET_KEY'] = 'a-very-temporary-secret-key-please-change'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "instance", "traffic_app.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

db = SQLAlchemy(app)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Create directories if they don't exist ---
# Ensure the instance directory exists for SQLite DB creation
os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
# Ensure upload/output base directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# --- Database Models ---
class ProcessingStatus(enum.Enum):
    PENDING_CONFIG = "PENDING_CONFIG"
    PENDING_FILES = "PENDING_FILES"
    READY_TO_PROCESS = "READY_TO_PROCESS"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"

class Study(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    scenarios = db.relationship('Scenario', backref='study', lazy=True, cascade="all, delete-orphan")

class Scenario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    study_id = db.Column(db.Integer, db.ForeignKey('study.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False) # e.g., existing, build_phase_1
    status = db.Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING_CONFIG)
    status_message = db.Column(db.String(255), nullable=True) # Store error details

    # Store relative paths from BASE_DIR
    am_csv_path = db.Column(db.String(255), nullable=True)
    pm_csv_path = db.Column(db.String(255), nullable=True)
    attout_txt_path = db.Column(db.String(255), nullable=True)
    merged_csv_path = db.Column(db.String(255), nullable=True)
    attin_txt_path = db.Column(db.String(255), nullable=True)

    # Ensure unique scenario names within a study
    __table_args__ = (db.UniqueConstraint('study_id', 'name', name='_study_scenario_uc'),)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_scenario_folder_path(study_id, scenario_id, folder_type="uploads"):
    """
    Generates a structured path for scenario files.
    Example: ./uploads/1/5/ or ./outputs/1/5/
    """
    base_folder = UPLOAD_FOLDER if folder_type == "uploads" else OUTPUT_FOLDER
    # Use study_id and scenario_id for better organization
    path = os.path.join(base_folder, str(study_id), str(scenario_id))
    os.makedirs(path, exist_ok=True) # Ensure the specific scenario directory exists
    return path

# --- Core Processing Logic ---
def process_traffic_data(am_csv_path, pm_csv_path, attout_txt_path, output_dir, scenario_name):
    """
    Processes AM/PM CSVs and ATTOUT file to generate Merged CSV and ATTIN TXT.

    Args:
        am_csv_path (str): Absolute path to the AM CSV file.
        pm_csv_path (str): Absolute path to the PM CSV file.
        attout_txt_path (str): Absolute path to the ATTOUT TXT file.
        output_dir (str): Absolute path to the directory to save output files.
        scenario_name (str): Name of the scenario for output file naming.

    Returns:
        tuple: (merged_csv_output_path, attin_txt_output_path) or raises Exception on error.
    """
    logging.info(f"Starting processing for scenario: {scenario_name}")
    logging.info(f"AM Path: {am_csv_path}")
    logging.info(f"PM Path: {pm_csv_path}")
    logging.info(f"ATTOUT Path: {attout_txt_path}")
    logging.info(f"Output Dir: {output_dir}")

    # Expected columns (adjust if needed based on exact input variations)
    MOVEMENT_COLS = ['EBU','EBL','EBT','EBR','WBU','WBL','WBT','WBR','NBU','NBL','NBT','NBR','SBU','SBL','SBT','SBR']
    # Check for minimum required columns in input CSVs
    MIN_INPUT_COLS = ['RECORDNAME', 'INTID'] + MOVEMENT_COLS
    ATTOUT_MIN_COLS = ['HANDLE', 'BLOCKNAME', 'NODE_ID'] # ATTOUT movements checked dynamically

    try:
        # 1. Read AM Volume Data
        logging.info("Reading AM CSV...")
        df_am = pd.read_csv(am_csv_path, dtype={'INTID': str}) # Read INTID as string
        if not all(col in df_am.columns for col in MIN_INPUT_COLS):
             col_list_str = ", ".join(MIN_INPUT_COLS)
             raise ValueError(f"AM CSV is missing required columns. Expected at least: {col_list_str}")
        df_am = df_am[df_am['RECORDNAME'] == 'Volume'].copy()
        df_am = df_am[['INTID'] + MOVEMENT_COLS] # Select only needed columns
        df_am = df_am.set_index('INTID')
        # Handle potential '-' or blanks and convert to numeric (NaN if error)
        for col in MOVEMENT_COLS:
            # errors='coerce' turns invalid parsing into NaN (Not a Number)
            df_am[col] = pd.to_numeric(df_am[col], errors='coerce')
        df_am = df_am.add_suffix('_am')
        logging.info(f"Read {len(df_am)} AM volume records.")

        # 2. Read PM Volume Data
        logging.info("Reading PM CSV...")
        df_pm = pd.read_csv(pm_csv_path, dtype={'INTID': str}) # Read INTID as string
        if not all(col in df_pm.columns for col in MIN_INPUT_COLS):
             col_list_str = ", ".join(MIN_INPUT_COLS)
             raise ValueError(f"PM CSV is missing required columns. Expected at least: {col_list_str}")
        df_pm = df_pm[df_pm['RECORDNAME'] == 'Volume'].copy()
        df_pm = df_pm[['INTID'] + MOVEMENT_COLS]
        df_pm = df_pm.set_index('INTID')
        # Handle potential '-' or blanks and convert to numeric (NaN if error)
        for col in MOVEMENT_COLS:
            df_pm[col] = pd.to_numeric(df_pm[col], errors='coerce')
        df_pm = df_pm.add_suffix('_pm')
        logging.info(f"Read {len(df_pm)} PM volume records.")

        # 3. Merge AM and PM Data
        logging.info("Merging AM and PM data...")
        # Use outer merge to keep nodes present in only one file (will result in NaN for missing side)
        df_merged = pd.merge(df_am, df_pm, left_index=True, right_index=True, how='outer')
        logging.info(f"Merged data has {len(df_merged)} nodes.")

        # Create AM(PM) strings, handling NaN (missing values)
        merged_cols_map = {} # To store mapping from original movement name to merged column name
        for move in MOVEMENT_COLS:
            col_am = f'{move}_am'
            col_pm = f'{move}_pm'
            col_merged = f'{move}_merged'
            merged_cols_map[move] = col_merged # Store for later lookup

            # Function to format AM(PM) string, handling NaN correctly
            def format_ampm(row):
                am_val = row[col_am]
                pm_val = row[col_pm]
                # pd.isna checks for NaN (which represents missing/unparseable data here)
                am_str = str(int(am_val)) if pd.notna(am_val) else '-'
                pm_str = str(int(pm_val)) if pd.notna(pm_val) else '-'
                return f"{am_str}({pm_str})"

            # Apply the function row-wise to create the merged column
            df_merged[col_merged] = df_merged.apply(format_ampm, axis=1)

        # 4. Prepare Merged CSV Output
        # Create a secure filename for the output
        merged_csv_filename = f"{secure_filename(scenario_name)}_Merged.csv"
        merged_csv_output_path = os.path.join(output_dir, merged_csv_filename)
        # Select only the '_merged' columns we created, using the map to ensure correct order initially
        df_merged_output = df_merged[[merged_cols_map[m] for m in MOVEMENT_COLS]].copy()
        df_merged_output.index.name = 'Node ID' # Set index name for CSV header
        # Rename columns back to original movement names (e.g., 'EBU_merged' -> 'EBU')
        df_merged_output.rename(columns=lambda x: x.replace('_merged', ''), inplace=True)
        # Save to CSV
        df_merged_output.to_csv(merged_csv_output_path, index=True)
        logging.info(f"Merged CSV saved to: {merged_csv_output_path}")

        # 5. Read ATTOUT Data and Header
        logging.info("Reading ATTOUT TXT...")
        try:
            with open(attout_txt_path, 'r', encoding='utf-8') as f: # Added encoding
                attout_lines = f.readlines()
        except FileNotFoundError:
             raise ValueError(f"ATTOUT file not found at {attout_txt_path}")
        except Exception as e:
             raise ValueError(f"Error reading ATTOUT file: {e}")


        if not attout_lines:
            raise ValueError("ATTOUT file is empty.")

        # Assume first line is header, tab-delimited
        attout_header_raw = attout_lines[0].strip()
        if '\t' not in attout_header_raw:
             # Handle case where maybe it's comma or space delimited? For now, strict tab.
             raise ValueError("ATTOUT file does not appear to be tab-delimited based on the header line.")
        attout_header = [h.strip() for h in attout_header_raw.split('\t')]
        logging.info(f"ATTOUT Header: {attout_header}")

        # Validate minimum required ATTOUT columns
        if not all(col in attout_header for col in ATTOUT_MIN_COLS):
            missing_cols = [col for col in ATTOUT_MIN_COLS if col not in attout_header]
            raise ValueError(f"ATTOUT file header is missing required columns: {', '.join(missing_cols)}")

        # Identify the order of movement tags from the ATTOUT header
        # Filter header list to only include known movement columns
        attout_movement_order = [col for col in attout_header if col in MOVEMENT_COLS]
        if len(attout_movement_order) != 16:
             logging.warning(f"ATTOUT header contains {len(attout_movement_order)} recognized movement tags, expected 16. Found: {attout_movement_order}. ATTIN generation might be incomplete.")
             # Decide if this is critical. For now, proceed with found movements.
             # If strict 16 needed: raise ValueError("ATTOUT header does not contain exactly 16 recognized movement tags.")

        # Parse ATTOUT data rows (skip header)
        attout_data = []
        for i, line in enumerate(attout_lines[1:]):
            line_content = line.strip()
            if not line_content: continue # Skip empty lines
            # Ensure splitting by tab; handle potential extra whitespace if needed
            parts = [p.strip() for p in line_content.split('\t')]
            if len(parts) != len(attout_header):
                logging.warning(f"Skipping ATTOUT line {i+2}: Incorrect number of columns ({len(parts)}), expected {len(attout_header)}. Line content: '{line_content}'")
                continue
            # Create a dictionary for easier access by column name
            row_data = dict(zip(attout_header, parts))
            attout_data.append(row_data)
        logging.info(f"Read {len(attout_data)} data rows from ATTOUT.")


        # 6. Generate ATTIN TXT Output
        logging.info("Generating ATTIN TXT...")
        # Create secure filename for ATTIN output
        attin_txt_filename = f"{secure_filename(scenario_name)}_ATTIN.txt"
        attin_txt_output_path = os.path.join(output_dir, attin_txt_filename)
        attin_lines = []
        processed_handles = set()
        nodes_not_found_in_merge = []
        handles_missing_data = [] # Track handles skipped

        # Convert merged data to dictionary for faster lookup by Node ID (index)
        merged_data_dict = df_merged[[merged_cols_map[m] for m in MOVEMENT_COLS]].to_dict('index')

        for att_row in attout_data:
            handle = att_row.get('HANDLE')
            blockname = att_row.get('BLOCKNAME')
            node_id_str = att_row.get('NODE_ID') # Node ID from ATTOUT

            # Basic validation of required fields from ATTOUT row
            if not handle or not blockname or not node_id_str:
                logging.warning(f"Skipping ATTOUT row due to missing HANDLE, BLOCKNAME, or NODE_ID: {att_row}")
                handles_missing_data.append(str(att_row.get('HANDLE', 'UNKNOWN')))
                continue

            # Check for duplicate handles processed
            if handle in processed_handles:
                logging.warning(f"Duplicate HANDLE '{handle}' found in ATTOUT file. Skipping subsequent occurrences.")
                continue
            processed_handles.add(handle)

            # Look up merged data using Node ID from ATTOUT
            merged_node_data = merged_data_dict.get(node_id_str)

            if merged_node_data:
                # Build the line parts for the ATTIN file
                # Order: HANDLE, BLOCKNAME, NODE_ID, then movements in ATTOUT order
                attin_row_parts = [handle, blockname, node_id_str]
                # Iterate through movement columns IN THE ORDER SPECIFIED BY ATTOUT HEADER
                for move_attout_order in attout_movement_order:
                    # Find the corresponding column name in our merged dataframe (e.g., 'EBU_merged')
                    merged_col_name = merged_cols_map.get(move_attout_order)

                    if merged_col_name:
                        # Get the 'AM(PM)' value from the merged data for this node
                        value = merged_node_data.get(merged_col_name)

                        # --- Crucial Handling for ATTIN Output ---
                        # Check if the value represents missing data based on our format_ampm function
                        # or if the merge resulted in NaN for this node/movement.
                        # ATTIN requires empty string "" for missing attributes.
                        if value == "-(-)" or pd.isna(value):
                            attin_row_parts.append("") # Use empty string for missing
                        else:
                            # Keep values like '10(-)', '-(5)', '0(0)', '123(456)'
                            attin_row_parts.append(str(value))
                    else:
                        # This case should ideally not happen if MOVEMENT_COLS is correct
                        logging.warning(f"Movement '{move_attout_order}' from ATTOUT header not found in internal map for HANDLE '{handle}'. Appending empty string.")
                        attin_row_parts.append("")

                # Join the parts with tabs to form the ATTIN line
                attin_lines.append("\t".join(attin_row_parts))
            else:
                # Node ID from ATTOUT row was not found in the merged AM/PM data
                nodes_not_found_in_merge.append(node_id_str)
                handles_missing_data.append(handle)
                logging.warning(f"Node ID '{node_id_str}' (HANDLE: {handle}) from ATTOUT not found in merged volume data. Skipping ATTIN line.")


        # Report summary of issues
        if nodes_not_found_in_merge:
             logging.warning(f"Summary: {len(set(nodes_not_found_in_merge))} unique Node IDs from ATTOUT were not found in the merged AM/PM data: {list(set(nodes_not_found_in_merge))}")
             logging.warning(f"Summary: ATTIN lines were not generated for {len(set(handles_missing_data))} unique HANDLEs due to missing Node IDs or other data issues.")


        # Write the ATTIN file (no header row)
        with open(attin_txt_output_path, 'w', encoding='utf-8') as f: # Added encoding
            f.write("\n".join(attin_lines))

        logging.info(f"ATTIN TXT saved to: {attin_txt_output_path}")
        logging.info(f"Processing complete for scenario: {scenario_name}")
        return merged_csv_output_path, attin_txt_output_path

    except FileNotFoundError as e:
        logging.error(f"File not found error during processing: {e}")
        raise Exception(f"Input file not found: {e.filename}") from e
    except pd.errors.EmptyDataError as e:
        # Find which file was empty if possible (needs more context)
        logging.error(f"Empty CSV or TXT file error: {e}")
        raise Exception(f"Input file is empty or invalid.") from e
    except ValueError as e: # Catch specific data/format errors raised
        logging.error(f"Data validation error during processing: {e}")
        raise Exception(f"Data Format Error: {e}") from e
    except KeyError as e: # Catch missing columns in DataFrames
        logging.error(f"Missing expected column or key error: {e}")
        raise Exception(f"Missing expected data column: {e}") from e
    except Exception as e: # Catch any other unexpected errors
        logging.exception(f"An unexpected error occurred during processing scenario {scenario_name}") # Log full traceback
        raise Exception(f"An unexpected error occurred: {e}") from e


# --- API Endpoints ---

@app.route('/api/studies', methods=['POST'])
def create_study():
    data = request.get_json()
    if not data or not data.get('name'): # Check specifically for name
        return jsonify({"error": "Study 'name' is required in JSON body"}), 400
    study_name = data['name'].strip()
    if not study_name:
         return jsonify({"error": "Study 'name' cannot be empty"}), 400

    if Study.query.filter_by(name=study_name).first():
         return jsonify({"error": f"Study name '{study_name}' already exists"}), 409 # Conflict

    try:
        new_study = Study(name=study_name)
        db.session.add(new_study)
        db.session.commit()
        logging.info(f"Created study '{study_name}' with ID {new_study.id}")
        return jsonify({"message": "Study created", "study_id": new_study.id, "name": new_study.name}), 201
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error creating study '{study_name}'")
        return jsonify({"error": f"Database error creating study: {e}"}), 500


@app.route('/api/studies/<int:study_id>/configure', methods=['POST'])
def configure_study(study_id):
    # Find the study or return 404
    study = db.session.get(Study, study_id) # Use db.session.get for primary key lookup
    if not study:
        return jsonify({"error": f"Study with ID {study_id} not found."}), 404

    data = request.get_json()
    if not data or 'phases_n' not in data:
        return jsonify({"error": "'phases_n' (number of phases) is required in JSON body"}), 400

    try:
        n = int(data['phases_n'])
        if n < 0: raise ValueError("Number of phases cannot be negative.")
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid number for 'phases_n': {e}"}), 400

    # Optional scenario flags (default to false if not provided, ensure boolean)
    def get_bool_param(param_name):
         val = data.get(param_name, False)
         return str(val).lower() in ['true', '1', 'yes']

    include_bg_dist = get_bool_param('include_bg_dist')
    include_bg_assign = get_bool_param('include_bg_assign')
    include_trip_dist = get_bool_param('include_trip_dist')
    include_trip_assign = get_bool_param('include_trip_assign')

    # --- Delete existing scenarios for this study before adding new ones ---
    # WARNING: This is destructive. Add checks/confirmation in a real app.
    try:
        num_deleted = Scenario.query.filter_by(study_id=study_id).delete()
        # TODO: Also delete associated files from storage (uploads/outputs)
        logging.info(f"Deleted {num_deleted} existing scenarios for study {study_id} before reconfiguration.")

        scenarios_to_create = []
        # Always add Existing
        scenarios_to_create.append(Scenario(study_id=study.id, name='Existing', status=ProcessingStatus.PENDING_FILES))

        # Add phase-based scenarios
        for i in range(1, n + 1):
            scenarios_to_create.append(Scenario(study_id=study.id, name=f'No_Build_Phase_{i}', status=ProcessingStatus.PENDING_FILES))
            scenarios_to_create.append(Scenario(study_id=study.id, name=f'Build_Phase_{i}', status=ProcessingStatus.PENDING_FILES))
            if include_bg_dist:
                 scenarios_to_create.append(Scenario(study_id=study.id, name=f'Background_Development_Distribution_Phase_{i}', status=ProcessingStatus.PENDING_FILES))
            if include_bg_assign:
                 scenarios_to_create.append(Scenario(study_id=study.id, name=f'Background_Development_Assignment_Phase_{i}', status=ProcessingStatus.PENDING_FILES))
            if include_trip_dist:
                 scenarios_to_create.append(Scenario(study_id=study.id, name=f'Trip_Distribution_Phase_{i}', status=ProcessingStatus.PENDING_FILES))
            if include_trip_assign:
                 scenarios_to_create.append(Scenario(study_id=study.id, name=f'Trip_Assignment_Phase_{i}', status=ProcessingStatus.PENDING_FILES))

        db.session.add_all(scenarios_to_create)
        db.session.commit()

        logging.info(f"Configured study {study_id} with N={n} phases and options. Total scenarios added: {len(scenarios_to_create)}")
        # Fetch the created scenarios to return their details
        created_scenarios = Scenario.query.filter_by(study_id=study_id).order_by(Scenario.id).all()
        scenario_list = [{"id": s.id, "name": s.name, "status": s.status.name} for s in created_scenarios]

        return jsonify({
            "message": f"Study configured with {len(scenario_list)} scenarios.",
            "scenarios": scenario_list
            }), 200
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error configuring study {study_id}")
        return jsonify({"error": f"Database error configuring scenarios: {e}"}), 500


@app.route('/api/studies/<int:study_id>/scenarios', methods=['GET'])
def get_scenarios(study_id):
    # Ensure study exists
    study = db.session.get(Study, study_id)
    if not study:
        return jsonify({"error": f"Study with ID {study_id} not found."}), 404

    scenarios = Scenario.query.filter_by(study_id=study_id).order_by(Scenario.id).all()
    scenario_list = [
        {"id": s.id, "name": s.name, "status": s.status.name, "status_message": s.status_message,
         # Check if path exists and is not empty string
         "has_am_csv": bool(s.am_csv_path),
         "has_pm_csv": bool(s.pm_csv_path),
         "has_attout": bool(s.attout_txt_path),
         "has_merged": bool(s.merged_csv_path),
         "has_attin": bool(s.attin_txt_path)}
        for s in scenarios
    ]
    return jsonify(scenario_list)


@app.route('/api/studies/<int:study_id>/scenarios/<int:scenario_id>/upload', methods=['POST'])
def upload_scenario_file(study_id, scenario_id):
    # Find the specific scenario or return 404
    scenario = Scenario.query.filter_by(id=scenario_id, study_id=study_id).first()
    if not scenario:
         return jsonify({"error": f"Scenario with ID {scenario_id} not found for study {study_id}."}), 404

    if scenario.status in [ProcessingStatus.PROCESSING]: # Prevent upload during processing
         return jsonify({"error": "Cannot upload files while scenario is processing."}), 409 # Conflict

    file_type = request.form.get('file_type') # Expected: 'am_csv', 'pm_csv', 'attout_txt'
    if not file_type or file_type not in ['am_csv', 'pm_csv', 'attout_txt']:
        return jsonify({"error": "Missing or invalid 'file_type' in form data (must be 'am_csv', 'pm_csv', or 'attout_txt')"}), 400

    if 'file' not in request.files:
        return jsonify({"error": "No 'file' part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected for upload"}), 400

    if file and allowed_file(file.filename):
        # Create a more descriptive filename (type_originalName)
        # Use secure_filename on the original filename part only
        safe_original_filename = secure_filename(file.filename)
        filename = f"{file_type}_{safe_original_filename}"

        # Get the specific directory for this scenario's uploads
        upload_path_dir = get_scenario_folder_path(study_id, scenario_id, folder_type="uploads")
        save_path = os.path.join(upload_path_dir, filename)
        # Store path relative to BASE_DIR in database for portability
        relative_save_path = os.path.relpath(save_path, BASE_DIR)

        try:
            # TODO: Before saving new, delete old file if it exists for this file_type?
            # Example: if file_type == 'am_csv' and scenario.am_csv_path: os.remove(os.path.join(BASE_DIR, scenario.am_csv_path))
            file.save(save_path)
            logging.info(f"Saved file '{filename}' to '{save_path}' for scenario {scenario_id} (type: {file_type})")

            # Update database record with the relative path
            if file_type == 'am_csv':
                scenario.am_csv_path = relative_save_path
            elif file_type == 'pm_csv':
                scenario.pm_csv_path = relative_save_path
            elif file_type == 'attout_txt':
                scenario.attout_txt_path = relative_save_path

            # Check if all files are present to update status
            if scenario.am_csv_path and scenario.pm_csv_path and scenario.attout_txt_path:
                # Only change status if it wasn't already complete or error (allow re-upload to fix errors)
                if scenario.status not in [ProcessingStatus.COMPLETE]:
                    scenario.status = ProcessingStatus.READY_TO_PROCESS
                    scenario.status_message = "All input files uploaded." # Clear previous errors
            else:
                 scenario.status = ProcessingStatus.PENDING_FILES
                 scenario.status_message = "Waiting for other input file(s)."

            db.session.commit()

            return jsonify({"message": f"File '{safe_original_filename}' uploaded successfully for type '{file_type}'.",
                            "saved_filename": filename,
                            "scenario_status": scenario.status.name}), 200
        except Exception as e:
            db.session.rollback() # Rollback DB changes if file save fails
            logging.exception(f"Error saving file for scenario {scenario_id}")
            return jsonify({"error": f"Could not save file: {e}"}), 500
    else:
        return jsonify({"error": f"File type not allowed (allowed: {', '.join(ALLOWED_EXTENSIONS)})"}), 400


@app.route('/api/studies/<int:study_id>/scenarios/<int:scenario_id>/process', methods=['POST'])
def process_scenario(study_id, scenario_id):
    # Find the specific scenario or return 404
    scenario = Scenario.query.filter_by(id=scenario_id, study_id=study_id).first()
    if not scenario:
         return jsonify({"error": f"Scenario with ID {scenario_id} not found for study {study_id}."}), 404


    # Check if scenario is in a state ready for processing
    if scenario.status not in [ProcessingStatus.READY_TO_PROCESS, ProcessingStatus.ERROR, ProcessingStatus.COMPLETE]:
        # Allow reprocessing if completed or had an error, otherwise must be READY
        return jsonify({"error": f"Scenario is not ready for processing. Status: {scenario.status.name}. Requires status READY_TO_PROCESS, ERROR, or COMPLETE."}), 409 # Conflict

    # Verify all file paths are actually set in the DB record
    if not all([scenario.am_csv_path, scenario.pm_csv_path, scenario.attout_txt_path]):
         scenario.status = ProcessingStatus.PENDING_FILES # Ensure status reflects reality
         db.session.commit()
         return jsonify({"error": "Cannot process: Missing one or more required input file paths in database record (AM CSV, PM CSV, ATTOUT TXT)."}), 400

    # --- IMPORTANT: Convert this block to use an ASYNCHRONOUS TASK QUEUE in production! ---
    # Set status to PROCESSING immediately
    scenario.status = ProcessingStatus.PROCESSING
    scenario.status_message = "Processing started..."
    # Clear previous output paths before starting
    scenario.merged_csv_path = None
    scenario.attin_txt_path = None
    db.session.commit()

    try:
        # Construct absolute paths from stored relative paths
        am_path = os.path.join(BASE_DIR, scenario.am_csv_path)
        pm_path = os.path.join(BASE_DIR, scenario.pm_csv_path)
        attout_path = os.path.join(BASE_DIR, scenario.attout_txt_path)
        # Get the specific output directory for this scenario
        output_dir_path = get_scenario_folder_path(study_id, scenario_id, folder_type="outputs")

        # Verify input files exist on disk before processing
        if not os.path.exists(am_path): raise FileNotFoundError(am_path)
        if not os.path.exists(pm_path): raise FileNotFoundError(pm_path)
        if not os.path.exists(attout_path): raise FileNotFoundError(attout_path)

        # Call the core processing function
        merged_path, attin_path = process_traffic_data(
            am_path, pm_path, attout_path, output_dir_path, scenario.name
        )

        # --- Processing Successful ---
        # Update scenario record with relative output paths and status
        scenario.merged_csv_path = os.path.relpath(merged_path, BASE_DIR)
        scenario.attin_txt_path = os.path.relpath(attin_path, BASE_DIR)
        scenario.status = ProcessingStatus.COMPLETE
        scenario.status_message = "Processing completed successfully."
        db.session.commit()
        logging.info(f"Successfully processed scenario {scenario_id} for study {study_id}")

        return jsonify({
            "message": "Scenario processing completed successfully.", # Message for sync completion
            "scenario_id": scenario.id,
            "status": scenario.status.name,
            "merged_csv_path": scenario.merged_csv_path, # Return relative paths
            "attin_txt_path": scenario.attin_txt_path
            }), 200

    except Exception as e:
        # --- Processing Failed ---
        db.session.rollback() # Rollback potential partial DB changes if something failed mid-process
        # Fetch the scenario again within this exception block's session context
        scenario = db.session.get(Scenario, scenario_id)
        scenario.status = ProcessingStatus.ERROR
        # Provide a user-friendly summary of the error
        scenario.status_message = f"Processing failed: {str(e)}"
        db.session.commit()
        # Log the full error for debugging
        logging.exception(f"Processing failed for scenario {scenario_id} (Study {study_id})")
        # Return 500 Internal Server Error for processing failures
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500
    # --- End of synchronous block ---


@app.route('/api/studies/<int:study_id>/scenarios/<int:scenario_id>/status', methods=['GET'])
def get_scenario_status(study_id, scenario_id):
    # Find the specific scenario or return 404
    scenario = Scenario.query.filter_by(id=scenario_id, study_id=study_id).first()
    if not scenario:
         return jsonify({"error": f"Scenario with ID {scenario_id} not found for study {study_id}."}), 404

    return jsonify({
        "scenario_id": scenario.id,
        "name": scenario.name,
        "status": scenario.status.name,
        "status_message": scenario.status_message,
        "has_merged": bool(scenario.merged_csv_path),
        "has_attin": bool(scenario.attin_txt_path)
        })

@app.route('/api/studies/<int:study_id>/scenarios/<int:scenario_id>/download/<file_type>', methods=['GET'])
def download_scenario_file(study_id, scenario_id, file_type):
    # Find the specific scenario or return 404
    scenario = Scenario.query.filter_by(id=scenario_id, study_id=study_id).first()
    if not scenario:
         return jsonify({"error": f"Scenario with ID {scenario_id} not found for study {study_id}."}), 404

    file_path_relative = None
    expected_filename_base = secure_filename(scenario.name) # Base name for download

    if file_type == 'attin':
        file_path_relative = scenario.attin_txt_path
        download_name = f"{expected_filename_base}_ATTIN.txt"
    elif file_type == 'merged':
        file_path_relative = scenario.merged_csv_path
        download_name = f"{expected_filename_base}_Merged.csv"
    # Add downloads for original uploads if needed
    elif file_type == 'am_csv':
         file_path_relative = scenario.am_csv_path
         # Extract original filename if stored like type_originalName
         download_name = os.path.basename(file_path_relative).split('_', 1)[-1] if '_' in os.path.basename(file_path_relative) else os.path.basename(file_path_relative)
    elif file_type == 'pm_csv':
         file_path_relative = scenario.pm_csv_path
         download_name = os.path.basename(file_path_relative).split('_', 1)[-1] if '_' in os.path.basename(file_path_relative) else os.path.basename(file_path_relative)
    elif file_type == 'attout_txt':
         file_path_relative = scenario.attout_txt_path
         download_name = os.path.basename(file_path_relative).split('_', 1)[-1] if '_' in os.path.basename(file_path_relative) else os.path.basename(file_path_relative)
    else:
        return jsonify({"error": "Invalid file type requested. Must be 'attin', 'merged', 'am_csv', 'pm_csv', or 'attout_txt'."}), 400

    if not file_path_relative:
         abort(404, f"File path for type '{file_type}' not found in database record for this scenario.")

    # Construct absolute path
    file_path_absolute = os.path.join(BASE_DIR, file_path_relative)
    directory = os.path.dirname(file_path_absolute)
    filename = os.path.basename(file_path_absolute) # The actual filename on disk

    # Check if file exists on disk *before* sending
    if not os.path.exists(file_path_absolute):
         logging.error(f"File path '{file_path_absolute}' found in DB but missing from disk for scenario {scenario_id}, type '{file_type}'.")
         # Optional: Update DB to reflect missing file? E.g., set path to None, status to ERROR?
         abort(404, f"Output file '{filename}' is missing from storage.")

    logging.info(f"Serving file: '{filename}' from dir: '{directory}' as download name: '{download_name}'")
    try:
        return send_from_directory(directory, filename, as_attachment=True, download_name=download_name)
    except Exception as e:
        logging.exception(f"Error sending file {filename} for download.")
        abort(500, "Server error occurred while trying to send the file.")


# --- Main Execution Guard ---
if __name__ == '__main__':
    # Ensure the app context is available for DB operations
    with app.app_context():
        # Create database tables based on models if they don't exist
        db.create_all()
    # Run the Flask development server
    # debug=True enables auto-reloading and provides detailed error pages
    # IMPORTANT: Turn debug OFF in production environments!
    app.run(debug=True, host='0.0.0.0', port=5000) # Listen on all interfaces