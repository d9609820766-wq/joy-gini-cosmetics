JOY GINI COSMETICS – Setup Instructions

1. Extract the project folder.
2. Open terminal / command prompt inside the folder.
3. Create a virtual environment (optional but recommended):
python -m venv venv
source venv/bin/activate (Linux/Mac)
venv\Scripts\activate (Windows)
4. Install dependencies:
pip install -r requirements.txt
5. Run the app:
python app.py
6. Open browser and go to: http://127.0.0.1:5000
7. Admin login URL: /admin/login
Default admin email: admin@joygini.com
Default admin password: admin123
(You can change after first login via database or settings panel later)

Features:
- Customer frontend: product listing, details (zoom, stock, order, share, reviews)
- Admin panel: products, stock (barcode/qr), billing, customers, orders, employees, settings (GST, logo, banners, social media)
- Mobile & desktop responsive: marron gradient + golden card borders

For deployment on a server, change host='0.0.0.0' and use a production WSGI server (gunicorn, waitress).