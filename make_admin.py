import sys
import os
sys.path.append(os.getcwd())
from app.database import SessionLocal, init_db
from app import models
from datetime import datetime

# Ensure DB is initialized
init_db()

db = SessionLocal()
email = 'aalsawalmeh1986@gmail.com'
user = db.query(models.User).filter(models.User.email == email).first()

if user:
    user.role = models.UserRole.ADMIN
    print(f"User {email} already exists. Role updated to ADMIN.")
else:
    user = models.User(
        email=email,
        first_name="Admin",
        last_name="User",
        role=models.UserRole.ADMIN,
        login_method="google",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        last_signed_in=datetime.utcnow()
    )
    db.add(user)
    print(f"User {email} created successfully with ADMIN role.")

db.commit()
db.close()
