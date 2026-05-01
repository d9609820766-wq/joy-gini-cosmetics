import os

class Config:
    SECRET_KEY = 'joy-gini-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///cosmetics.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    # App settings (will be stored in DB later, but defaults)
    STORE_NAME = "Joy Gini Cosmetics"
    STORE_ADDRESS = "Your Store Address Here"
    STORE_PHONE = "+91 9876543210"
    GST_RATE = 18   # default 18% (0 to 28)