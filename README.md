# RuralLearn Backend

A starter REST API for the RuralLearn virtual classroom project.

## Included
- Student and teacher registration/login
- Password hashing
- Teacher classroom creation and join codes
- Student join requests and teacher approval
- Recorded lesson links and notes
- Teacher/student dashboard summaries
- PostgreSQL on Render (SQLite is used for local testing if DATABASE_URL is not set)

## Deploy on Render
1. Upload the contents of this folder to the GitHub repository named `rurallearn-backend`.
2. In Render, choose **New +** → **Blueprint**.
3. Connect the GitHub repository and deploy the `render.yaml` blueprint.
4. Render creates the web service and PostgreSQL database. Copy the web service URL.

## API quick test
Open `https://YOUR-BACKEND-URL/` or `/api/health` in a browser. You should see a JSON status message.

### Register
POST `/api/register`
```json
{"name":"Teacher One","email":"teacher@example.com","password":"pass123","role":"teacher"}
```

### Login
POST `/api/login`
```json
{"email":"teacher@example.com","password":"pass123"}
```
Use the returned token in the `Authorization` header as `Bearer YOUR_TOKEN` for protected endpoints.

## Important
This is a starter backend. It stores lesson video links; it does not provide live video calling. The existing RuralLearn website frontend must be connected to these API endpoints before registration, login, and classroom features work on the website. Replace the default secret with a strong private value if deploying outside the supplied Render Blueprint.
