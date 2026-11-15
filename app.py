from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date, timedelta, datetime
import sqlite3
from pathlib import Path

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deployment"
DB_PATH = Path(__file__).with_name("performx.db")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('employee','manager','admin')),
            department TEXT NOT NULL DEFAULT 'General'
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            assigned_to INTEGER NOT NULL REFERENCES users(id),
            created_by INTEGER NOT NULL REFERENCES users(id),
            due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK(status IN ('Pending','In Progress','Completed')),
            quality_score INTEGER,
            manager_feedback TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Safe, additive migrations for existing databases.
        task_columns = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
        if "completed_at" not in task_columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
            conn.execute("""
                UPDATE tasks SET completed_at=created_at
                WHERE status='Completed' AND completed_at IS NULL
            """)
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            link TEXT NOT NULL DEFAULT '/dashboard',
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            leaderboard_visible INTEGER NOT NULL DEFAULT 1
        );
        """)
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            demo_users = [
                ("Aarav Sharma", "employee@performx.demo", generate_password_hash("demo123"), "employee", "Engineering"),
                ("Priya Verma", "manager@performx.demo", generate_password_hash("demo123"), "manager", "Engineering"),
                ("Admin User", "admin@performx.demo", generate_password_hash("demo123"), "admin", "Human Resources"),
                ("Rohan Mehta", "rohan@performx.demo", generate_password_hash("demo123"), "employee", "Engineering"),
            ]
            conn.executemany(
                "INSERT INTO users(name,email,password_hash,role,department) VALUES(?,?,?,?,?)",
                demo_users
            )
            employee_id = conn.execute("SELECT id FROM users WHERE email=?", ("employee@performx.demo",)).fetchone()["id"]
            rohan_id = conn.execute("SELECT id FROM users WHERE email=?", ("rohan@performx.demo",)).fetchone()["id"]
            manager_id = conn.execute("SELECT id FROM users WHERE email=?", ("manager@performx.demo",)).fetchone()["id"]
            today = date.today()
            sample_tasks = [
                ("Prepare API documentation", "Document the task-management API endpoints.", employee_id, manager_id, (today + timedelta(days=2)).isoformat(), "In Progress", None, ""),
                ("Resolve dashboard UI issue", "Fix alignment and responsive layout on the dashboard.", employee_id, manager_id, (today - timedelta(days=1)).isoformat(), "Completed", 4, "Good work; clear implementation."),
                ("Review database schema", "Review employee and task table relationships.", rohan_id, manager_id, (today + timedelta(days=4)).isoformat(), "Pending", None, ""),
                ("Write unit test cases", "Add tests for task status validation.", rohan_id, manager_id, (today + timedelta(days=1)).isoformat(), "Completed", 5, "Thorough test coverage."),
            ]
            conn.executemany("""
                INSERT INTO tasks(title,description,assigned_to,created_by,due_date,status,quality_score,manager_feedback)
                VALUES(?,?,?,?,?,?,?,?)
            """, sample_tasks)
        conn.execute("""
            INSERT OR IGNORE INTO user_preferences(user_id)
            SELECT id FROM users
        """)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("role") not in roles:
                flash("You don't have permission to access that page.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def performance_score(user_id, month_key=None):
    with db() as conn:
        if month_key:
            rows = conn.execute("""
                SELECT status, due_date, quality_score
                FROM tasks WHERE assigned_to=? AND substr(created_at,1,7)=?
            """, (user_id, month_key)).fetchall()
        else:
            rows = conn.execute("""
                SELECT status, due_date, quality_score
                FROM tasks WHERE assigned_to=?
            """, (user_id,)).fetchall()
    completed = [r for r in rows if r["status"] == "Completed"]
    if not rows:
        return 0
    completion_rate = len(completed) / len(rows) * 100
    rated = [r for r in completed if r["quality_score"] is not None]
    quality_rate = (sum(r["quality_score"] for r in rated) / (5 * len(rated)) * 100) if rated else 0
    on_time = sum(1 for r in completed if r["due_date"] >= date.today().isoformat())
    on_time_rate = (on_time / len(completed) * 100) if completed else 0
    return round(completion_rate * .4 + quality_rate * .4 + on_time_rate * .2)


def add_notification(user_id, title, message, link="/dashboard"):
    with db() as conn:
        conn.execute(
            "INSERT INTO notifications(user_id,title,message,link) VALUES(?,?,?,?)",
            (user_id, title, message, link)
        )


def achievement_for(score, completed, improvement=0):
    if improvement >= 10:
        return "Most Improved"
    if score >= 90:
        return "Quality Champion"
    if completed >= 3:
        return "Consistency Star"
    return "Rising Contributor"


def employee_metrics():
    with db() as conn:
        people = conn.execute("""
            SELECT u.id,u.name,u.department,
                   COUNT(t.id) AS total_tasks,
                   SUM(CASE WHEN t.status='Completed' THEN 1 ELSE 0 END) AS completed_tasks
            FROM users u LEFT JOIN tasks t ON u.id=t.assigned_to
            WHERE u.role='employee'
            GROUP BY u.id ORDER BY u.name
        """).fetchall()
    result = []
    for p in people:
        score = performance_score(p["id"])
        result.append({**dict(p), "total_tasks": p["total_tasks"] or 0,
                       "completed_tasks": p["completed_tasks"] or 0, "score": score})
    return result


@app.context_processor
def inject_notifications():
    if "user_id" not in session:
        return {}
    with db() as conn:
        unread = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (session["user_id"],)
        ).fetchone()[0]
    return {"unread_notifications": unread}


@app.route("/")
def home():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            session["department"] = user["department"]
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    role = session["role"]
    with db() as conn:
        if role == "employee":
            tasks = conn.execute("""
                SELECT tasks.*, users.name AS assignee
                FROM tasks JOIN users ON tasks.assigned_to=users.id
                WHERE assigned_to=? ORDER BY due_date
            """, (session["user_id"],)).fetchall()
            total = len(tasks)
            completed = sum(t["status"] == "Completed" for t in tasks)
            pending = sum(t["status"] != "Completed" for t in tasks)
            score = performance_score(session["user_id"])
            return render_template("employee.html", tasks=tasks, total=total,
                                   completed=completed, pending=pending, score=score)
        people = employee_metrics()
        task_rows = conn.execute("""
            SELECT tasks.*, users.name AS assignee
            FROM tasks JOIN users ON tasks.assigned_to=users.id
            ORDER BY tasks.due_date
        """).fetchall()
        stats = {
            "employees": len(people), "tasks": len(task_rows),
            "completed": sum(t["status"] == "Completed" for t in task_rows),
            "pending": sum(t["status"] != "Completed" for t in task_rows)
        }
    return render_template("manager.html" if role == "manager" else "admin.html",
                           employees=people, tasks=task_rows, stats=stats)


@app.route("/tasks/create", methods=["POST"])
@roles_required("manager", "admin")
def create_task():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    due_date = request.form.get("due_date", "")
    assigned_to = request.form.get("assigned_to", type=int)
    if not title or not due_date or not assigned_to:
        flash("Please complete all required task fields.", "error")
        return redirect(url_for("dashboard"))
    with db() as conn:
        employee = conn.execute("SELECT id,name FROM users WHERE id=? AND role='employee'", (assigned_to,)).fetchone()
        if not employee:
            flash("Select a valid employee.", "error")
            return redirect(url_for("dashboard"))
        conn.execute("""
            INSERT INTO tasks(title,description,assigned_to,created_by,due_date)
            VALUES(?,?,?,?,?)
        """, (title, description, assigned_to, session["user_id"], due_date))
        employee_name = employee["name"]
    add_notification(assigned_to, "New task assigned",
                    f"{title} was assigned to you by {session.get('name')}.",
                    "/dashboard")
    flash(f"Task assigned successfully to {employee_name}.", "success")
    return redirect(url_for("dashboard"))


@app.route("/tasks/<int:task_id>/status", methods=["POST"])
@roles_required("employee")
def update_status(task_id):
    status = request.form.get("status")
    if status not in ("Pending", "In Progress", "Completed"):
        flash("Invalid task status.", "error")
        return redirect(url_for("dashboard"))
    with db() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=? AND assigned_to=?",
                            (task_id, session["user_id"])).fetchone()
        if not task:
            flash("Task not found.", "error")
            return redirect(url_for("dashboard"))
        if status == "Completed":
            conn.execute("UPDATE tasks SET status=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                         (status, task_id))
        else:
            conn.execute("UPDATE tasks SET status=?, quality_score=NULL, completed_at=NULL WHERE id=?",
                         (status, task_id))
        manager_id = task["created_by"]
        task_title = task["title"]
    if status == "Completed":
        add_notification(manager_id, "Task completed",
                         f"{session.get('name')} completed: {task_title}.",
                         "/dashboard")
    flash("Task status updated.", "success")
    return redirect(url_for("dashboard"))


@app.route("/tasks/<int:task_id>/review", methods=["POST"])
@roles_required("manager", "admin")
def review_task(task_id):
    quality = request.form.get("quality_score", type=int)
    feedback = request.form.get("manager_feedback", "").strip()
    if quality not in range(1, 6):
        flash("Quality score must be between 1 and 5.", "error")
        return redirect(url_for("dashboard"))
    with db() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task or task["status"] != "Completed":
            flash("Only completed tasks can be reviewed.", "error")
            return redirect(url_for("dashboard"))
        conn.execute("UPDATE tasks SET quality_score=?, manager_feedback=? WHERE id=?",
                     (quality, feedback, task_id))
        employee_id = task["assigned_to"]
        title = task["title"]
    add_notification(employee_id, "Task review received",
                     f"Your manager reviewed “{title}”. Open your dashboard to see the result.",
                     "/dashboard")
    flash("Task review saved.", "success")
    return redirect(url_for("dashboard"))


@app.route("/employees")
@roles_required("manager", "admin")
def employees():
    result = employee_metrics()
    return render_template("employees.html", employees=result)


@app.route("/team")
@login_required
def team_performance():
    people = employee_metrics()
    # Employees see aggregate work metrics only; private manager feedback is never queried here.
    return render_template("team.html", employees=people)


@app.route("/leaderboard", methods=["GET", "POST"])
@login_required
def leaderboard():
    if request.method == "POST":
        if session.get("role") != "employee":
            flash("Only employees can change their leaderboard visibility.", "error")
            return redirect(url_for("leaderboard"))
        visible = 1 if request.form.get("leaderboard_visible") == "1" else 0
        with db() as conn:
            conn.execute("""
                INSERT INTO user_preferences(user_id,leaderboard_visible) VALUES(?,?)
                ON CONFLICT(user_id) DO UPDATE SET leaderboard_visible=excluded.leaderboard_visible
            """, (session["user_id"], visible))
        flash("Leaderboard preference updated.", "success")
        return redirect(url_for("leaderboard"))
    with db() as conn:
        preference = conn.execute(
            "SELECT leaderboard_visible FROM user_preferences WHERE user_id=?",
            (session["user_id"],)
        ).fetchone()
        visible = bool(preference["leaderboard_visible"]) if preference else True
        rows = conn.execute("""
            SELECT u.id,u.name,u.department,p.leaderboard_visible,
                   COUNT(t.id) AS total_tasks,
                   SUM(CASE WHEN t.status='Completed' THEN 1 ELSE 0 END) AS completed_tasks
            FROM users u
            JOIN user_preferences p ON p.user_id=u.id
            LEFT JOIN tasks t ON t.assigned_to=u.id
            WHERE u.role='employee' AND p.leaderboard_visible=1
            GROUP BY u.id ORDER BY u.name
        """).fetchall()
    ranked = []
    current_month = date.today().strftime("%Y-%m")
    for row in rows:
        score = performance_score(row["id"], current_month)
        ranked.append({**dict(row), "score": score,
                       "completed_tasks": row["completed_tasks"] or 0,
                       "total_tasks": row["total_tasks"] or 0})
    ranked.sort(key=lambda x: (x["score"], x["completed_tasks"]), reverse=True)
    for index, person in enumerate(ranked, 1):
        person["rank"] = index
        person["badge"] = achievement_for(person["score"], person["completed_tasks"])
    return render_template("leaderboard.html", employees=ranked, leaderboard_visible=visible,
                           current_month=date.today().strftime("%B %Y"))


@app.route("/progress")
@roles_required("employee")
def personal_progress():
    user_id = session["user_id"]
    with db() as conn:
        monthly = conn.execute("""
            SELECT substr(created_at,1,7) AS month_key, COUNT(*) AS assigned,
                   SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed
            FROM tasks WHERE assigned_to=? AND substr(created_at,1,7)>=?
            GROUP BY substr(created_at,1,7) ORDER BY month_key
        """, (user_id, (date.today().replace(day=1) - timedelta(days=155)).strftime("%Y-%m"))).fetchall()
        completed_this_month = conn.execute("""
            SELECT COUNT(*) FROM tasks WHERE assigned_to=? AND status='Completed'
            AND substr(COALESCE(completed_at,created_at),1,7)=?
        """, (user_id, date.today().strftime("%Y-%m"))).fetchone()[0]
        total_completed = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE assigned_to=? AND status='Completed'", (user_id,)
        ).fetchone()[0]
    months = [{"label": datetime.strptime(r["month_key"], "%Y-%m").strftime("%b %Y"),
               "assigned": r["assigned"], "completed": r["completed"] or 0} for r in monthly]
    return render_template("progress.html", months=months,
                           completed_this_month=completed_this_month,
                           total_completed=total_completed,
                           score=performance_score(user_id))


@app.route("/notifications")
@login_required
def notifications():
    with db() as conn:
        rows = conn.execute("""
            SELECT * FROM notifications WHERE user_id=?
            ORDER BY created_at DESC,id DESC LIMIT 100
        """, (session["user_id"],)).fetchall()
    return render_template("notifications.html", notifications=rows)


@app.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    with db() as conn:
        conn.execute("""
            UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?
        """, (notification_id, session["user_id"]))
        row = conn.execute(
            "SELECT link FROM notifications WHERE id=? AND user_id=?",
            (notification_id, session["user_id"])
        ).fetchone()
    return redirect(row["link"] if row else url_for("notifications"))


@app.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_all_notifications_read():
    with db() as conn:
        conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (session["user_id"],))
    flash("All notifications marked as read.", "success")
    return redirect(url_for("notifications"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
