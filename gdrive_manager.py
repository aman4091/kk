#!/usr/bin/env python3
"""
Google Drive Image Manager
Fetch and delete images from Google Drive for video generation
"""

import os
import pickle
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials


class GDriveImageManager:
    def __init__(self, token_path='token.pickle'):
        """Initialize Google Drive manager with existing credentials"""
        self.token_path = token_path
        self.service = None
        self._load_credentials()

    def _load_credentials(self):
        """Load Google Drive credentials from token.pickle"""
        try:
            # Try multiple paths for token.pickle
            search_paths = [
                self.token_path,
                '../token.pickle',  # Parent directory (common on Vast.ai)
                'token.pickle',
                os.path.join(os.path.dirname(__file__), 'token.pickle'),
                os.path.join(os.path.dirname(__file__), '../token.pickle')
            ]

            token_found = None
            for path in search_paths:
                if os.path.exists(path):
                    token_found = path
                    break

            if not token_found:
                print(f"❌ Token file not found in any of these paths:")
                for p in search_paths:
                    print(f"   - {os.path.abspath(p)}")
                return

            self.token_path = token_found
            print(f"✅ Found token.pickle at: {token_found}")

            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)

            # Build service
            self.service = build('drive', 'v3', credentials=creds)
            print("✅ GDrive credentials loaded")

        except Exception as e:
            print(f"❌ GDrive credentials load error: {e}")

    def list_images_in_folder(self, folder_id, max_results=10):
        """
        List image files in a Google Drive folder

        Args:
            folder_id: Google Drive folder ID
            max_results: Maximum number of images to fetch

        Returns:
            list: List of image file metadata dicts
        """
        try:
            if not self.service:
                print("❌ GDrive service not initialized")
                return []

            # Query: Images in folder (JPEG, PNG, JPG)
            query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/jpg') and trashed=false"

            results = self.service.files().list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, mimeType, createdTime)"
            ).execute()

            files = results.get('files', [])

            if not files:
                print(f"⚠️ No images found in folder: {folder_id}")
                return []

            print(f"✅ Found {len(files)} image(s) in folder")
            return files

        except Exception as e:
            print(f"❌ GDrive list error: {e}")
            return []

    def fetch_multiple_images_from_folder(self, folder_id, count=10, download_dir='output/images'):
        """
        Fetch multiple images from Google Drive folder for transitions

        Args:
            folder_id: Google Drive folder ID
            count: Number of images to fetch
            download_dir: Local directory to download images

        Returns:
            tuple: (list of local_image_paths, list of gdrive_file_ids) or ([], []) if failed
        """
        try:
            # List images
            images = self.list_images_in_folder(folder_id, max_results=count)

            if not images:
                print("❌ No images available in folder")
                return [], []

            # Ensure download directory exists
            os.makedirs(download_dir, exist_ok=True)

            local_paths = []
            file_ids = []

            for i, image in enumerate(images[:count]):
                file_id = image['id']
                file_name = image['name']

                print(f"📥 Fetching image {i+1}/{count}: {file_name}")

                # Download image
                local_path = os.path.join(download_dir, f"multi_{i+1}_{file_name}")
                success = self.download_file(file_id, local_path)

                if success:
                    local_paths.append(local_path)
                    file_ids.append(file_id)
                else:
                    print(f"⚠️ Failed to download image {i+1}, skipping")

            if local_paths:
                print(f"✅ Downloaded {len(local_paths)} images")
                return local_paths, file_ids
            else:
                return [], []

        except Exception as e:
            print(f"❌ Multi-image fetch error: {e}")
            return [], []

    def fetch_next_image_from_folder(self, folder_id, download_dir='output/images'):
        """
        Fetch the first image from Google Drive folder
        (User will manage folder - add images manually)

        Args:
            folder_id: Google Drive folder ID
            download_dir: Local directory to download image

        Returns:
            tuple: (local_image_path, gdrive_file_id) or (None, None) if failed
        """
        try:
            # List images
            images = self.list_images_in_folder(folder_id, max_results=1)

            if not images:
                print("❌ No images available in folder")
                return None, None

            # Get first image
            image = images[0]
            file_id = image['id']
            file_name = image['name']

            print(f"📥 Fetching image: {file_name} (ID: {file_id})")

            # Ensure download directory exists
            os.makedirs(download_dir, exist_ok=True)

            # Download image
            local_path = os.path.join(download_dir, file_name)
            success = self.download_file(file_id, local_path)

            if success:
                print(f"✅ Image downloaded: {local_path}")
                return local_path, file_id
            else:
                return None, None

        except Exception as e:
            print(f"❌ Image fetch error: {e}")
            return None, None

    def download_file(self, file_id, local_path):
        """
        Download a file from Google Drive

        Args:
            file_id: Google Drive file ID
            local_path: Local path to save file

        Returns:
            bool: True if successful
        """
        try:
            if not self.service:
                print("❌ GDrive service not initialized")
                return False

            # Download file
            request = self.service.files().get_media(fileId=file_id)
            fh = io.FileIO(local_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            fh.close()
            return True

        except Exception as e:
            print(f"❌ GDrive download error: {e}")
            return False

    def delete_image_from_gdrive(self, file_id):
        """
        Delete an image from Google Drive after use

        Args:
            file_id: Google Drive file ID

        Returns:
            bool: True if successful
        """
        try:
            if not self.service:
                print("❌ GDrive service not initialized")
                return False

            self.service.files().delete(fileId=file_id).execute()
            print(f"✅ Deleted image from GDrive: {file_id}")
            return True

        except Exception as e:
            print(f"❌ GDrive delete error: {e}")
            return False

    def get_folder_info(self, folder_id):
        """
        Get folder name and metadata

        Args:
            folder_id: Google Drive folder ID

        Returns:
            dict: Folder metadata or None
        """
        try:
            if not self.service:
                print("❌ GDrive service not initialized")
                return None

            folder = self.service.files().get(
                fileId=folder_id,
                fields="id, name, mimeType"
            ).execute()

            print(f"✅ Folder: {folder['name']} (ID: {folder['id']})")
            return folder

        except Exception as e:
            print(f"❌ GDrive folder info error: {e}")
            return None

    def create_folder(self, folder_name, parent_folder_id=None):
        """
        Create a new folder in Google Drive

        Args:
            folder_name: Name of folder to create
            parent_folder_id: Optional parent folder ID

        Returns:
            str: New folder ID or None if failed
        """
        try:
            if not self.service:
                print("❌ GDrive service not initialized")
                return None

            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]

            folder = self.service.files().create(
                body=file_metadata,
                fields='id, name'
            ).execute()

            print(f"✅ Created folder: {folder_name} (ID: {folder['id']})")
            return folder['id']

        except Exception as e:
            print(f"❌ GDrive folder creation error: {e}")
            return None

    def folder_exists(self, folder_name, parent_folder_id):
        """
        Check if folder exists in parent folder

        Args:
            folder_name: Name of folder to check
            parent_folder_id: Parent folder ID

        Returns:
            str: Folder ID if exists, None otherwise
        """
        try:
            if not self.service:
                return None

            query = f"name='{folder_name}' and '{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"

            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=1
            ).execute()

            items = results.get('files', [])

            if items:
                return items[0]['id']
            return None

        except Exception as e:
            print(f"❌ Folder existence check error: {e}")
            return None

    def get_or_create_folder(self, folder_name, parent_folder_id):
        """
        Get existing folder or create if doesn't exist

        Args:
            folder_name: Name of folder
            parent_folder_id: Parent folder ID

        Returns:
            str: Folder ID
        """
        existing_id = self.folder_exists(folder_name, parent_folder_id)
        if existing_id:
            return existing_id
        return self.create_folder(folder_name, parent_folder_id)

    def copy_file(self, file_id, destination_folder_id, new_name=None):
        """
        Copy a file to a different folder in Google Drive

        Args:
            file_id: Source file ID
            destination_folder_id: Destination folder ID
            new_name: Optional new name for the copy

        Returns:
            str: New file ID or None if failed
        """
        try:
            if not self.service:
                print("❌ GDrive service not initialized")
                return None

            # Prepare file metadata
            file_metadata = {
                'parents': [destination_folder_id]
            }

            if new_name:
                file_metadata['name'] = new_name

            # Copy file
            copied_file = self.service.files().copy(
                fileId=file_id,
                body=file_metadata,
                fields='id, name'
            ).execute()

            print(f"✅ Copied file to folder: {copied_file['name']} (ID: {copied_file['id']})")
            return copied_file['id']

        except Exception as e:
            print(f"❌ GDrive file copy error: {e}")
            return None

    def upload_text_file(self, text_content, folder_id, filename):
        """
        Upload text content as a file to Google Drive

        Args:
            text_content: Text content to upload
            folder_id: Destination folder ID
            filename: Name of file

        Returns:
            str: File ID or None if failed
        """
        try:
            if not self.service:
                print("❌ GDrive service not initialized")
                return None

            import io
            from googleapiclient.http import MediaIoBaseUpload

            # Create file metadata
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }

            # Create file content
            fh = io.BytesIO(text_content.encode('utf-8'))
            media = MediaIoBaseUpload(fh, mimetype='text/plain', resumable=True)

            # Upload file
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name'
            ).execute()

            print(f"✅ Uploaded text file: {filename} (ID: {file['id']})")
            return file['id']

        except Exception as e:
            print(f"❌ GDrive text upload error: {e}")
            return None

    def delete_folder(self, folder_id):
        """
        Delete a folder from Google Drive (moves to trash)

        Args:
            folder_id: Google Drive folder ID

        Returns:
            bool: True if successful
        """
        try:
            if not self.service:
                print("❌ GDrive service not initialized")
                return False

            self.service.files().delete(fileId=folder_id).execute()
            print(f"✅ Deleted folder from GDrive: {folder_id}")
            return True

        except Exception as e:
            print(f"❌ GDrive folder delete error: {e}")
            return False

    def upload_file(self, file_path, folder_id, filename=None):
        """
        Upload a file to Google Drive

        Args:
            file_path: Local file path
            folder_id: Destination folder ID
            filename: Optional custom filename (default: use original name)

        Returns:
            str: File ID or None if failed
        """
        try:
            if not self.service:
                print("❌ GDrive service not initialized")
                return None

            import os
            from googleapiclient.http import MediaFileUpload

            # Use original filename if not specified
            if not filename:
                filename = os.path.basename(file_path)

            # Detect MIME type
            import mimetypes
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = 'application/octet-stream'

            # Create file metadata
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }

            # Upload file
            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name'
            ).execute()

            print(f"✅ Uploaded file: {filename} (ID: {file['id']})")
            return file['id']

        except Exception as e:
            print(f"❌ GDrive file upload error: {e}")
            return None


# Example usage
if __name__ == '__main__':
    # Initialize manager
    manager = GDriveImageManager()

    # Test folder ID (replace with actual folder ID)
    test_folder_id = "YOUR_FOLDER_ID_HERE"

    # Get folder info
    print("\n1. Getting folder info...")
    folder = manager.get_folder_info(test_folder_id)

    # List images
    print("\n2. Listing images...")
    images = manager.list_images_in_folder(test_folder_id)
    for img in images:
        print(f"   - {img['name']} ({img['id']})")

    # Fetch first image
    print("\n3. Fetching first image...")
    image_path, file_id = manager.fetch_next_image_from_folder(test_folder_id)

    if image_path:
        print(f"   Downloaded: {image_path}")

        # Delete image
        print("\n4. Deleting image...")
        manager.delete_image_from_gdrive(file_id)
    else:
        print("   No image fetched")
