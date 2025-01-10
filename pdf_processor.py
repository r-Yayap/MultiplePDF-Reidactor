#pdf_processor.py

import os
import re
import pymupdf as fitz
import logging
from datetime import datetime
import multiprocessing
from functools import partial
from utils import adjust_coordinates_for_rotation, adjust_point_for_rotation

class PDFProcessor:
    def __init__(self, pdf_folder, output_excel_path, areas, insertion_points, include_subfolders, table_coordinates, rev_coordinates,revision_date, revision_description):

        self.insertion_points = insertion_points  # Store insertion points

        self.table_coordinates = table_coordinates  # Add table coordinates
        self.rev_coordinates = rev_coordinates  # Add revision coordinates
        self.revision_date = revision_date  # Store Date
        self.revision_description = revision_description

        self.log_file = None  # Log file will be set during setup_logging()

        self.pdf_folder = pdf_folder
        self.output_excel_path = output_excel_path
        self.areas = areas
        self.include_subfolders = include_subfolders
        self.temp_image_folder = "temp_images"
        self.headers = ["Size (Bytes)", "Date Last Modified", "Folder", "Filename", "Page No"] + \
                       [f"{area['title']}" if "title" in area else f"Area {i + 1}" for i, area in enumerate(self.areas)]

        if not os.path.exists(self.temp_image_folder):
            os.makedirs(self.temp_image_folder)

    def setup_logging(self):
        """Configures the logging module with a dynamic log file name."""
        log_folder = "logs"  # Define a folder for logs
        os.makedirs(log_folder, exist_ok=True)

        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = os.path.join(log_folder, f"error_log_{current_time}.txt")

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(self.log_file, mode='w'),
                logging.StreamHandler()
            ]
        )
        print(f"Logging initialized. Log file: {self.log_file}")

    def clean_text(self, text):
        """Cleans text by replacing newlines, stripping, and removing illegal characters."""
        replacement_char = '■'  # Character to replace prohibited control characters

        # Step 1: Replace newline and carriage return characters with a space
        text = text.replace('\n', ' ').replace('\r', ' ')

        # Step 2: Strip leading and trailing whitespace
        text = text.strip()

        # Step 3: Replace prohibited control characters with a replacement character
        text = re.sub(r'[\x00-\x1F\x7F-\x9F]', replacement_char, text)

        # Step 4: Remove extra spaces between words
        return re.sub(r'\s+', ' ', text)

    def start_processing(self, progress_list, total_files):
        """Extracts text from PDFs using multiprocessing and updates the progress list."""
        log_file = self.setup_logging()  # Call logging setup
        logging.info(f"Logging started. Log file: {log_file}")

        try:
            # Gather all PDF files in the specified folder
            pdf_files = self.get_pdf_files()
            total_files.value = len(pdf_files)

            if not pdf_files:
                logging.warning("No PDF files found in the specified folder.")
                return

            # Create a multiprocessing pool
            pool = multiprocessing.Pool()
            manager = multiprocessing.Manager()
            progress_list = manager.list()  # Shared list for progress tracking

            # Use partial to pass the shared progress list to process_single_pdf
            process_func = partial(self.process_single_pdf, progress_list=progress_list)

            # Process the files in parallel
            pool.map(process_func, pdf_files)

            # Close and join the pool
            pool.close()
            pool.join()

            logging.info(f"Processed {len(progress_list)} out of {len(pdf_files)} PDFs.")

        except Exception as e:
            logging.error(f"Error during processing: {e}")

    def insert_revision_row(self, page, table, new_row, latest_revision_index):
            """Insert a new revision row using precise cell bounding boxes."""
            cell_text = table.extract()  # Extract table contents
            cell_boxes = [[cell for cell in row.cells] for row in table.rows]  # Get cell bounding boxes

            num_cols = len(cell_text[0]) if cell_text else 0
            insert_row_index = latest_revision_index - 1

            if insert_row_index < 0:
                logging.warning("No valid row for insertion.")
                return

            for col_index, cell_content in enumerate(new_row):
                if col_index < num_cols:
                    cell_box = cell_boxes[insert_row_index][col_index]
                    x0, y0, x1, y1 = cell_box
                    text_x0 = x0 + 2  # Adjust offset for better placement
                    text_y1 = y1 + 50
                    rect = fitz.Rect(text_x0, y0, x1, text_y1)

                    # Insert text into the cell
                    page.insert_textbox(
                        rect,
                        cell_content,
                        fontsize=8,
                        fontname="helv",
                        align=0  # Left-aligned
                    )

    def process_single_pdf(self, input_pdf_path, log_file, error_files, progress_list=None):
        """Reconfigures logging and processes a single PDF file."""

        logging.basicConfig(
            level=logging.WARNING,  # Log only warnings and errors
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(log_file, mode='a')]
        )

        try:
            output_pdf_path = self.get_output_path(input_pdf_path)
            doc = fitz.open(input_pdf_path)

            for page in doc:
                page.remove_rotation()

                for area in self.areas:
                    coordinates = area["coordinates"]
                    adjusted_coordinates = adjust_coordinates_for_rotation(
                        coordinates, page.rotation, page.rect.height, page.rect.width
                    )
                    rect = fitz.Rect(*adjusted_coordinates)
                    page.add_redact_annot(rect)

                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE | 0, graphics=fitz.PDF_REDACT_LINE_ART_NONE | 0)

                for insertion in self.insertion_points:
                    original_x, original_y = insertion['position']
                    adjusted_x, adjusted_y = adjust_point_for_rotation(
                        (original_x, original_y),
                        page.rotation,
                        page.rect.height,
                        page.rect.width
                    )
                    text = insertion['text']
                    font = insertion['font']
                    size = insertion['size']
                    page.insert_text(
                        (adjusted_x, adjusted_y),
                        text,
                        fontsize=size,
                        fontname=font,
                        rotate=page.rotation
                    )


                # Revision updater logic
                tables = page.find_tables(clip=self.table_coordinates, strategy="lines")
                if not tables.tables:  # Check if the tables list is empty
                    logging.warning(f"No tables found on page {page.number + 1} of {input_pdf_path}.")
                    continue

                if tables.tables:  # Check if there are any tables
                    for tab in tables.tables:
                        cell_text = tab.extract()
                        if not cell_text:
                            logging.warning(f"Empty table data on page {page.number + 1}.")
                            continue

                        latest_revision_index, last_revision = None, None
                        for row_index, row in enumerate(cell_text):
                            if row[0] and row[0].startswith("P"):
                                latest_revision_index = row_index
                                last_revision = row[0]
                                break

                        if latest_revision_index is not None and last_revision is not None:
                            try:

                                # Extract the previous values for columns 4 and 5
                                previous_col4 = cell_text[latest_revision_index][3] if len(cell_text[latest_revision_index]) > 3 else ""
                                previous_col5 = cell_text[latest_revision_index][4] if len(cell_text[latest_revision_index]) > 4 else ""

                                # Increment revision number and create new revision row
                                last_revision_number = int(last_revision[1:])
                                next_revision = f"P{last_revision_number + 1:02d}"
                                new_row = [next_revision, self.revision_date, self.revision_description, previous_col4,
                                           previous_col5]

                                # Insert the new row
                                self.insert_revision_row(page, tab, new_row, latest_revision_index)

                                # Redact and update revision area
                                page.add_redact_annot(fitz.Rect(*self.rev_coordinates))
                                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
                                page.insert_textbox(
                                    fitz.Rect(*self.rev_coordinates),
                                    next_revision,
                                    fontsize=8,
                                    fontname="helv",
                                    color=(0, 0, 0),
                                    align=1
                                )
                            except ValueError as e:
                                print(f"Revision processing error: {e}")


            doc.save(output_pdf_path)
            if progress_list is not None:
                progress_list.append(input_pdf_path)

        except Exception as e:
            logging.error(f"Error processing {input_pdf_path}: {e}")
            error_files.append(input_pdf_path)  # Add to error list

    def get_pdf_files(self):
        """Gathers all PDF files within the specified folder."""
        pdf_files = []
        for root_folder, subfolders, files in os.walk(self.pdf_folder):
            if not self.include_subfolders:
                subfolders.clear()
            pdf_files.extend(
                [os.path.join(root_folder, f) for f in files if f.lower().endswith('.pdf')]
            )
        return pdf_files

    def get_output_path(self, input_pdf_path):
        """
        Generates an output path for the redacted PDF, preserving the folder structure.
        """
        # Use the selected output folder for PDFs
        output_base_dir = self.output_excel_path  # Previously relied on output_excel_path for Excel

        # Calculate the relative path of the input file from the base folder
        relative_path = os.path.relpath(input_pdf_path, self.pdf_folder)

        # Generate the full output path, preserving subfolder structure
        output_path = os.path.join(output_base_dir, relative_path)

        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        return output_path
