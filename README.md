# TMCBubbleMaker
# Traffic Volume Bubble Web Application - User Guide

## 🧭 Overview

Welcome! This guide explains how to use the Traffic Volume Web App. Its purpose is to help you efficiently process raw AM/PM peak hour traffic volume data and generate correctly formatted files (`ATTIN.txt`) needed to update traffic volume bubble diagrams in your AutoCAD drawings.

The application supports managing multiple traffic **Studies** (or projects), each containing various **Scenarios** (like Existing conditions, future Build/No-Build phases, etc.).

## ✅ Prerequisites

Before you begin, you **must** have the following files prepared and ready for **each scenario** you plan to process within your study:

1.  **AM Peak Hour CSV (`.csv`):**
    *   Comma-separated values.
    *   Must contain columns: `RECORDNAME`, `INTID`, and the 16 standard movement volume columns (`EBU`, `EBL`, ..., `SBR`).
    *   Crucially, includes rows where `RECORDNAME` is `Volume` for the intersections (`INTID`). Other rows (like `PHF`, `HeavyVehicles`) can be present but will be ignored for volume merging.
    *   Ensure `INTID` matches the Node IDs used in your AutoCAD blocks/ATTOUT file.

2.  **PM Peak Hour CSV (`.csv`):**
    *   Same format as the AM CSV, but containing the PM peak hour volumes.

3.  **AutoCAD Attribute Out File (`.txt`):**
    *   **Tab-delimited** text file.
    *   Generated from the specific AutoCAD drawing for **that scenario** using the `ATTOUT` command.
    *   **Crucially contains:**
        *   A header row defining the exact attribute tag names and their order.
        *   Required columns in the header: `HANDLE`, `BLOCKNAME`, `NODE_ID`.
        *   The 16 movement attribute tags (e.g., `SBU`, `EBT`, `WBL`...) **in the specific order they appear in your AutoCAD block definition**. This order dictates the final `ATTIN` file structure.
    *   Data rows contain the `HANDLE` (unique block identifier), `BLOCKNAME`, `NODE_ID`, and current attribute values for each relevant block instance.

*(Refer to the initial technical specification document for detailed examples of these file formats if needed.)*

## 🚀 Workflow Steps

Follow these steps to process your traffic data:

1.  **Access the Web App:** Open the application in your web browser.

2.  **Select or Create a Study:**
    *   Choose an existing **Study** from a list, OR
    *   Create a **New Study** and give it a descriptive name (e.g., "Project X Traffic Analysis").

3.  **Configure Scenarios:**
    *   Once inside your study, locate the section for scenario configuration (e.g., "Configure Scenarios", "Define Phases").
    *   Enter the **Number of Phases (N)** required for your No-Build and Build analyses (e.g., enter `2` if you have Phase 1 and Phase 2).
    *   If prompted, select **Yes/No** for any additional optional scenario types you need (e.g., "Include Trip Distribution?", "Include Background Assignment?").
    *   Click the **"Configure"** or **"Save Configuration"** button.
    *   The application will generate sections/cards for each defined scenario (e.g., `Existing`, `No_Build_Phase_1`, `Build_Phase_1`, `Trip_Assignment_Phase_1`, etc.).

4.  **Upload Files for EACH Scenario:**
    *   Navigate through the different scenario sections displayed.
    *   **For each scenario section, independently:**
        *   Click the "Upload AM CSV" button/area and select the correct **AM Peak Hour CSV** file *for that specific scenario*.
        *   Click the "Upload PM CSV" button/area and select the correct **PM Peak Hour CSV** file *for that specific scenario*.
        *   Click the "Upload ATTOUT" button/area and select the correct **ATTOUT TXT** file *for that specific scenario*.
    *   *Repeat this upload process for every scenario defined in your study.*

5.  **Check Status and Preview (Optional):**
    *   As you upload files, the status for each scenario should update (e.g., "Pending Files", "Ready to Process").
    *   If available, use any "Preview Merged" or "Preview ATTIN" buttons to get a quick look at the data format before full processing. This can help catch potential formatting issues early.

6.  **Process EACH Scenario:**
    *   Once a scenario shows "Ready to Process" (meaning all 3 required files are uploaded), click its corresponding **"Process"** button.
    *   The scenario status will change to "Processing". This may take a few moments depending on file size.
    *   Upon completion, the status should change to **"Complete"**.
    *   If the status changes to **"Error"**, read the associated status message for details on what went wrong (e.g., missing columns, file not found, Node ID mismatch). Correct the input files and re-upload if necessary, then click "Process" again.
    *   *Repeat the processing step for every scenario you need results for.*

7.  **Download Output Files:**
    *   For any scenario marked as "Complete", locate the download options.
    *   Click the button to download the **`[ScenarioName]_ATTIN.txt`** file. This is the primary file needed for AutoCAD.
    *   You may also have an option to download the **`[ScenarioName]_Merged.csv`** file for review or other purposes.

8.  **Import Data into AutoCAD:**
    *   Open the AutoCAD drawing file that corresponds to the processed scenario (e.g., the drawing for Build Phase 1).
    *   Use the AutoCAD command `ATTIN`.
    *   When prompted, select the **`[ScenarioName]_ATTIN.txt`** file you downloaded in the previous step.
    *   AutoCAD will read the file and update the attributes of the traffic bubble blocks based on the `HANDLE` identifiers and the data provided. Verify the bubbles are updated correctly.

## 📝 Important Notes

*   **Node ID Matching:** Ensure the `INTID` values in your AM/PM CSV files exactly match the `NODE_ID` values in your ATTOUT file and the corresponding attribute within your AutoCAD blocks. Mismatches will prevent data from being associated correctly.
*   **ATTOUT Order is Critical:** The order of the movement attribute tags in your `ATTOUT.txt` header *absolutely dictates* the order of values in the generated `ATTIN.txt`. The web app uses the ATTOUT file from *each specific scenario* to determine the correct order for *that scenario's* ATTIN file.
*   **One Scenario at a Time:** Each scenario section (Existing, Build Phase 1, etc.) is processed independently using its own set of uploaded AM, PM, and ATTOUT files.
*   **Status Messages:** Pay attention to the status messages for each scenario, especially if an error occurs. They provide clues about potential problems with your input files or the processing itself.
*   **File Naming:** Downloaded files will follow a `ScenarioName_FileType.ext` pattern (e.g., `Build_Phase_1_ATTIN.txt`).

## 🤔 Troubleshooting

*   **Error Status:** If processing results in an "Error", check the status message. Most often, errors relate to:
    *   Incorrect file format (e.g., CSV not comma-delimited, ATTOUT not tab-delimited).
    *   Missing required columns in input files.
    *   Mismatched Node IDs between ATTOUT and CSVs.
    *   Empty input files.
    *   Correct the identified issue in your source file(s), re-upload them for that scenario, and try processing again.
*   **Data Not Updating in AutoCAD:**
    *   Verify you imported the correct `ATTIN.txt` file for the correct drawing/scenario.
    *   Double-check that the `HANDLE` values in the `ATTIN.txt` file match the handles of the blocks in your current AutoCAD drawing session.
    *   Confirm the `NODE_ID` attribute in your blocks matches the `NODE_ID` used in the processing.

---
