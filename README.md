RescueBite – Real-Time Food Donation & NGO Coordination Platform
RescueBite is a real-time digital platform designed to reduce food waste and improve food distribution by connecting Donors, Volunteers, and Receivers (NGOs) on a single web application.

The system enables donors to post surplus food, automatically finds the nearest NGOs, and assigns volunteers with locations using map-based navigation.

🚀 Project Overview
RescueBite works with three main user roles:

Donor – Posts available food for donation and tracks donation history
Receiver (NGO) – Views and accepts nearby food donations
Volunteer – Collects and delivers food using map-based navigation
The platform is built as a RESTful web application with secure authentication and role-based access.

🧩 Key Features
🔐 Authentication & Authorization
User registration and login using Django Authentication
Role-based access control (Donor / NGO / Volunteer)
Secure session management
🍱 Donor Module
Post food donation details
Automatic detection of nearest NGOs
Donation count tracking for potential future tax benefits in future
🏥 Receiver (NGO) Module
View nearby food listings
Accept or reject donation requests
Manage received donations
🚴 Volunteer Module
View accepted delivery tasks
Map-based route display using OpenStreetMap + Leaflet
Credit system for completed deliveries (retention model)
🌍 Map & Location Features
Real-time location-based food listing
Route visualization for volunteers
Navigation using Leaflet
🛠️ Tech Stack
Frontend
HTML
CSS
Bootstrap
Backend
Django
Django REST Framework
JavaScript
Tools & Libraries
Leaflet.js
OpenStreetMap
Git & GitHub
🗺️ System Architecture
RESTful APIs built using Django REST Framework
Role-based dashboards for each user type
Secure authentication using Django Auth system
Map integration for real-time navigation and routing
⚙️ How to Run Locally
Prerequisites
Python (for Django)
Git
Steps
git clone https://github.com/Yash132004/rescuebite.git
cd myproject
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
Then open: http://127.0.0.1:8000/

🌐 Live Demo

Deployed on free hosting: [https://rescuebite-uufn.onrender.com/]

💡 Future Enhancements

Government tax-relief integration for donors

Advanced route optimization

Push notifications for NGOs and volunteers

Partner restaurant integration for volunteer rewards

🤝 Contribution

Contributions, suggestions, and feedback are welcome! Feel free to fork this repository and raise a pull request.

📄 License

This project is open-source and available under the MIT License.

👤 Author

Yash Ojha GitHub: [https://github.com/Yash132004] LinkedIn: [https://www.linkedin.com/in/yash-ojha-23883b31a/]
