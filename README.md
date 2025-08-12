# Workshop Management System with Certificate Generation

This is a Flask-based web application for managing workshops, supporting two user roles:

- **Organizers**: Create workshops, view registrations and attendance.
- **Participants**: Register for workshops, mark attendance, and download personalized certificates of completion.

---

## Features

- User authentication with role-based access control (Organizers and Participants).
- Workshop creation, listing, and registration.
- Attendance marking (manual).
- Participant dashboard to view registered workshops and attendance.
- Certificate generation as downloadable PDF.
- MongoDB for data persistence.

---

## Tech Stack

- **Backend:** Python, Flask
- **Database:** MongoDB
- **Authentication:** Session-based with password hashing (Werkzeug)
- **Certificate Generation:** Pillow (PIL)
- **QR Codes:** qrcode library
- **Templates:** Jinja2 (Flask)
- **Environment Management:** python-dotenv

---

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/yourusername/workshop-management.git
    cd workshop-management
    ```

2. Create and activate a virtual environment:
    ```bash
    python3 -m venv venv
    source venv/bin/activate   # On Windows: venv\Scripts\activate
    ```

3. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4. Setup environment variables:

    Create a `.env` file in the root directory with the following variables:

    ```
    MONGO_URI=your_mongodb_connection_string
    SECRET_KEY=your_secret_key
    ```

5. Place the following assets inside the `static` folder:

    - `certificate_template.png` — Certificate background image.
    - `fonts/arial.ttf` — TrueType font file for rendering text on the certificate.

---

## Running the Application

Start the Flask development server:

```bash
python app.py

