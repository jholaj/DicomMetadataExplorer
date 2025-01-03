# DICOM Metadata Explorer

DICOM Metadata Explorer is a graphical desktop application designed for viewing, managing, and analyzing DICOM files.

## Features
- **Load, Edit & Save DICOM Files**: Easily load, edit one or more DICOM files and save them as needed.
- **Thumbnail View**: The left panel displays thumbnails of DICOM images organized by `StudyInstanceUID`.
- **Metadata Viewer**: Viewer & editor for DICOM tags.
- **Image Viewer**: Support for displaying image content with zoom functionality.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/jholaj/DicomMetadataExplorer.git
   cd DicomMetadataExplorer

2. Set up a Python virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt

4. Run the application:
   ```bash
   python main.py

## How to Use
1. Launch the application.
2. Use the Open button on the toolbar to load one or more DICOM files.
3. View thumbnails in the left panel. Click a thumbnail to display its content and metadata.
4. Switch between the Metadata and Content tabs to explore the file.
5. Save changes using the Save button.

## Screenshots
#### Metadata viewer
![Metadata viewer](https://i.imgur.com/zSbuMUG.png)
#### Editing tags
![Tags Editor](https://i.imgur.com/BCLl152.png)
#### Content viewer
![Content viewer](https://i.imgur.com/ObhVkTS.png)

## Notes
- The current version is intended for use with CR/DX modalities only.
- The application supports DICOM files with uncompressed pixel data or those compressed using supported formats (e.g., JPEG Lossless). Ensure dependencies like `pylibjpeg` or `gdcm` are installed for proper handling of compressed files.
- Thumbnail generation may fail for some DICOM files without valid pixel data or unsupported compression.
- This tool is for research and educational purposes; it is not suitable for clinical decision-making.

## License
This project is licensed under the MIT License.
