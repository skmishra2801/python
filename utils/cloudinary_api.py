import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()

# Configure Cloudinary globally
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

def upload_to_cloudinary(file_path, public_id=None):
    """Uploads file to Cloudinary and returns its secure URL."""
    try:
        response = cloudinary.uploader.upload(
            file_path,
            public_id=public_id,
            folder="cricket_players",
            overwrite=True
        )
        return response["secure_url"]
    except Exception as e:
        print("Cloudinary upload failed:", e)
        return None
