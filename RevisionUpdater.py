#revision_updater.py

import os

import pymupdf as fitz  # PyMuPDF
from multiprocessing import Pool, Manager
import logging

# input_pdf_folder = r'C:\Users\dae0519\Desktop\RRR\_PyProject\Xtractor-Multiprocessing\MultiplePDF-ReplaceTexts\Sample\01 - Architecture\2. PDF'
# output_pdf_folder = r'C:\Users\dae0519\Desktop\RRR\_PyProject\Xtractor-Multiprocessing\MultiplePDF-ReplaceTexts\Sample\01 - Architecture\Output'

input_pdf_folder = r'C:\Users\dae0519\Desktop\TestHaven'
output_pdf_folder = r'C:\Users\dae0519\Desktop\TestHaven-output'


table_coordinates = [2068, 829.5, 2331, 1000]  # [x0, y0, x1, y1]
rev_coordinates = [2298, 1613, 2326, 1640]

# Configure logging
log_file = "process_log.txt"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, mode='w'),
        logging.StreamHandler()
    ]
)


def insert_revision_row(page, tab, new_row, latest_revision_index):
    """Insert a new revision row using precise cell bounding boxes."""
    cell_text = tab.extract()  # Get cell contents
    cell_boxes = [[cell for cell in row.cells] for row in tab.rows]  # Get cell bounding boxes

    num_cols = len(cell_text[0]) if cell_text else 0

    # Identify the row to insert the new revision
    insert_row_index = latest_revision_index - 1
    if insert_row_index < 0:
        # print("No valid row for insertion.")
        return

    for col_index, cell_content in enumerate(new_row):
        if col_index < num_cols:
            # Get the bounding box for the target cell in the insertion row
            cell_box = cell_boxes[insert_row_index][col_index]
            x0, y0, x1, y1 = cell_box

            # Apply a slight offset and adjust font size
            offset = 2  # Adjust as needed
            text_x0 = x0 + offset  # Add a small horizontal offset
            text_y1 = y1 + 50

            rect = fitz.Rect(text_x0, y0, x1, text_y1)

            # print(f"Inserting text '{cell_content}' in textbox {rect}")
            page.insert_textbox(
                rect,
                cell_content,
                fontsize=8,
                fontname="helv",
                color=(0, 0, 0),
                align=0  # Align text to the left
            )


def process_pdf(input_path, output_path, results):
    """Process a single PDF."""
    try:
        doc = fitz.open(input_path)

        for page_number in range(len(doc)):
            page = doc[page_number]
            page.remove_rotation()
            # print(f"Processing page {page_number + 1} of {input_path}...")

            tables = page.find_tables(clip=table_coordinates, strategy="lines")  # Detect tables

            if not tables:
                logging.warning(f"No tables found on page {page_number + 1} of {input_path}.")
                continue

            for table_index, tab in enumerate(tables):
                # print(f"\nTable {table_index + 1}:")
                cell_text = tab.extract()  # Get cell contents
                # cell_boxes = [[cell for cell in row.cells] for row in tab.rows]  # Get cell bounding boxes
                # print(f"Extracted table content ({len(cell_text)} rows): {cell_text}")

                # Find the latest revision
                latest_revision_index = None
                last_revision = None
                for row_index, row in enumerate(cell_text):
                    if row[0] and row[0].startswith("P"):  # Check for the latest revision
                        latest_revision_index = row_index
                        last_revision = row[0]  # Get the last revision (e.g., "P05")
                        break

                if latest_revision_index is not None and last_revision is not None:
                    # Determine the next sequential revision
                    try:
                        last_revision_number = int(last_revision[1:])  # Extract numeric part
                        next_revision = f"P{last_revision_number + 1:02d}"  # Increment and format
                    except ValueError:
                        # print(f"Invalid revision format: {last_revision}")
                        continue

                    # Define the new revision row content
                    new_row = [next_revision, "09-Jan-25", "Issued for Tender", "", ""]
                    insert_revision_row(page, tab, new_row, latest_revision_index)

                    # Redact the area at rev_coordinates and insert the new revision
                    # print(f"Redacting and updating revision at {rev_coordinates}")
                    page.add_redact_annot(fitz.Rect(*rev_coordinates))
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

                    # Insert the new revision text
                    page.draw_rect(rev_coordinates)
                    page.insert_textbox(
                        fitz.Rect(*rev_coordinates),
                        next_revision,
                        fontsize=8,
                        fontname="helv",
                        color=(0, 0, 0),
                        align=1
                    )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)  # Ensure output folder exists
        doc.save(output_path)
        doc.close()

        logging.info(f"Successfully processed: {input_path}")
        results.put(("success", input_path))  # Send success to results queue

    except Exception as e:
        logging.error(f"Error processing {input_path}: {e}")
        results.put(("failed", input_path))  # Send failure to results queue


def process_all_pdfs(input_folder, output_folder):
    """Process all PDF files in the input folder using multiprocessing."""
    pdf_tasks = []

    for root, _, files in os.walk(input_folder):
        for file in files:
            if file.lower().endswith('.pdf'):
                input_path = os.path.join(root, file)
                relative_path = os.path.relpath(input_path, input_folder)
                output_path = os.path.join(output_folder, relative_path)
                pdf_tasks.append((input_path, output_path))

    # Use Manager to track results across processes
    manager = Manager()
    results = manager.Queue()

    # Create a multiprocessing pool
    with Pool() as pool:
        pool.starmap(process_pdf, [(input_path, output_path, results) for input_path, output_path in pdf_tasks])

    # Collect results
    success_count = 0
    failed_files = []

    while not results.empty():
        status, path = results.get()
        if status == "success":
            success_count += 1
        elif status == "failed":
            failed_files.append(path)

    # Log the summary
    logging.info(f"\nSummary:\n{'-'*40}")
    logging.info(f"Total files processed: {len(pdf_tasks)}")
    logging.info(f"Successfully processed: {success_count}")
    logging.info(f"Failed files: {len(failed_files)}")
    if failed_files:
        logging.info(f"Failed file paths:\n" + "\n".join(failed_files))


# Start processing all PDFs
if __name__ == "__main__":
    process_all_pdfs(input_pdf_folder, output_pdf_folder)