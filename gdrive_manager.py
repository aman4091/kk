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
            if not os.path.exists(self.token_path):
                print(f"❌ Token file not found: {self.token_path}")
                return

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
