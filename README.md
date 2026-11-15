# PerformX 2.0

A Flask + SQLite employee performance tracking demo.

## Existing features
- Employee, manager and admin demo accounts
- Role-protected dashboards
- Task assignment and employee status updates
- Manager quality reviews and feedback
- Performance score indicator

## PerformX 2.0 additions
- In-app notifications for new task assignments, task completion and manager reviews
- Team performance page with aggregate task metrics (private manager feedback is not exposed)
- Monthly leaderboard with employee opt-in / hide option
- Employee-only personal progress page with monthly task activity
- Notification history, unread count and mark-as-read actions

## Run locally (Windows PowerShell)
1. Open this folder in VS Code.
2. Create/activate a virtual environment if needed:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Start the app:
   ```powershell
   python app.py
   ```
5. Open http://127.0.0.1:5000

## Demo accounts
Password for all demo accounts: `demo123`

- Employee: `employee@performx.demo`
- Manager: `manager@performx.demo`
- Admin: `admin@performx.demo`
- Additional employee: `rohan@performx.demo`

## Database notes
The app performs additive SQLite migrations at startup. It adds notification, leaderboard preference and task completion timestamp fields without deleting existing users or tasks. Back up `performx.db` before replacing an existing project folder.

## Important
This is a demonstration app. The performance score is an illustrative indicator, not an automated HR or promotion decision. For production deployment, set a strong secret key, add CSRF protection, validate all inputs, and review authorization and privacy requirements.
