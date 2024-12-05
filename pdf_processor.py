#extractor.py

import os
import re
import pymupdf as fitz
from utils import adjust_coordinates_for_rotation, adjust_point_for_rotation


class PDFProcessor:
    def __init__(self, pdf_folder, output_excel_path, areas, insertion_points, ocr_settings, include_subfolders):

        self.insertion_points = insertion_points  # Store insertion points

        self.pdf_folder = pdf_folder
        self.output_excel_path = output_excel_path
        self.areas = areas
        self.ocr_settings = ocr_settings
        self.include_subfolders = include_subfolders
        self.tessdata_folder = find_tessdata() if ocr_settings["enable_ocr"] != "Off" else None
        self.temp_image_folder = "temp_images"
        self.headers = ["Size (Bytes)", "Date Last Modified", "Folder", "Filename", "Page No"] + \
                       [f"{area['title']}" if "title" in area else f"Area {i + 1}" for i, area in enumerate(self.areas)]

        if not os.path.exists(self.temp_image_folder):
            os.makedirs(self.temp_image_folder)

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
        """Extracts text from PDFs and updates the progress list."""
        try:
            # Gather all PDF files in the specified folder
            pdf_files = self.get_pdf_files()
            total_files.value = len(pdf_files)

            # Process each file
            for pdf_path in pdf_files:
                self.process_single_pdf(pdf_path, progress_list)

        except Exception as e:
            print(f"Error during extraction: {e}")

    def process_single_pdf(self, input_pdf_path, progress_list=None):
        """Redacts specified areas in a single PDF file."""
        try:
            # Generate output path
            output_pdf_path = self.get_output_path(input_pdf_path)

            # Open the PDF
            doc = fitz.open(input_pdf_path)

            for page in doc:
                # Apply redactions for each area
                for area in self.areas:
                    coordinates = area["coordinates"]
                    adjusted_coordinates = adjust_coordinates_for_rotation(
                        coordinates, page.rotation, page.rect.height, page.rect.width
                    )
                    rect = fitz.Rect(*adjusted_coordinates)
                    page.add_redact_annot(rect)

                # Apply the redactions on the page
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE | 0, graphics=fitz.PDF_REDACT_LINE_ART_NONE | 0)

                # Insert text into the PDF
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

                    # Insert the text into the PDF page
                    page.insert_text(
                        (adjusted_x, adjusted_y),
                        text,
                        fontsize=size,
                        fontname=font,
                        rotate=page.rotation
                    )

            # Save the redacted PDF
            doc.save(output_pdf_path)

            if progress_list is not None:
                progress_list.append(input_pdf_path)
        except Exception as e:
            print(f"Error processing {input_pdf_path}: {e}")

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
