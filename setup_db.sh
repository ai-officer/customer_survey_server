#!/bin/bash
# Run this once to create the PostgreSQL database and user.
# Requires sudo access or the postgres superuser account.

DB_NAME="customer_survey"
DB_USER="survey_user"
DB_PASSWORD="survey_pass"

echo "Creating PostgreSQL user and database..."

sudo -u postgres psql <<EOF
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
CREATE DATABASE $DB_NAME OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOF

echo "Done. Update backend/.env with:"
echo "DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
