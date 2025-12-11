from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash 
import os # ✅ नया: Environment variables (जैसे DATABASE_URL) पढ़ने के लिए

# --- App Configuration ---
app = Flask(__name__)
# SECRET_KEY को production में Environment Variable से लेना चाहिए
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'YOUR_HIGHLY_SECRET_KEY_HERE_CHANGE_ME_IN_PRODUCTION') 

# ✅ मुख्य बदलाव: DATABASE_URL को environment variable से लें।
# अगर DATABASE_URL नहीं मिलता है (जैसे लोकल टेस्टिंग में), तो sqlite का उपयोग करें।
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///habits.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_AS_ASCII'] = False 

db = SQLAlchemy(app)


# --- Database Models (No Change) ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    habits = db.relationship('Habit', backref='user', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        # Werkzeug 3.x के लिए यह सही है
        return check_password_hash(self.password_hash, password)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    goal_duration = db.Column(db.Integer, default=365) 
    start_date = db.Column(db.Date, default=date.today) 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) 
    
    completions = db.relationship('Completion', backref='habit', lazy=True, cascade="all, delete-orphan")

class Completion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'), nullable=False)

# --- Helper Function for Dates (No Change) ---
def get_seven_days():
    """Returns a list of the last 7 days starting from today."""
    today = date.today()
    days = [today - timedelta(days=i) for i in range(7)]
    return days[::-1]

# --- Authentication Routes (No Change) ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('signup'))
        
        if not username or not password:
             flash('Username and password are required.', 'danger')
             return redirect(url_for('signup'))

        new_user = User(username=username)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# --- Main Dashboard Route (Logic updated for 365 days and Pie Chart) ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        flash('Please log in to view your habits.', 'warning')
        return redirect(url_for('login'))
        
    user_id = session['user_id']

    if request.method == 'POST':
        habit_name = request.form.get('habit_name')
        goal_duration_str = request.form.get('goal_duration', '365') 
        
        try:
            goal_duration = int(goal_duration_str)
        except ValueError:
            goal_duration = 365 
            
        if habit_name:
            new_habit = Habit(name=habit_name, goal_duration=goal_duration, start_date=date.today(), user_id=user_id)
            db.session.add(new_habit)
            db.session.commit()
            return redirect(url_for('index'))
    
    habits = Habit.query.filter_by(user_id=user_id).all()
    seven_days = get_seven_days()
    
    habit_data = []
    for habit in habits:
        completed_dates = {comp.date for comp in habit.completions}
        
        # --- Goal Progress Calculation ---
        completed_count = Completion.query.filter_by(habit_id=habit.id).count()
        goal_status_text = f"{completed_count} / {habit.goal_duration} Days"
        progress_percent = min(100, int((completed_count / habit.goal_duration) * 100))
        daily_status = [day in completed_dates for day in seven_days]
        
        # --- PIE CHART DATA (Lifetime Performance) ---
        today = date.today()
        days_since_start = (today - habit.start_date).days + 1
        
        missed_days = days_since_start - completed_count
        missed_days = max(0, missed_days)
        
        if days_since_start > 0:
            completed_percent = round((completed_count / days_since_start) * 100, 1)
            missed_percent = round((missed_days / days_since_start) * 100, 1)
        else:
            completed_percent = 0
            missed_percent = 0

        pie_chart_data = [completed_percent, missed_percent]
        pie_chart_labels = ['Completed', 'Missed/Freez']

        
        # --- HEATMAP DATA CALCULATION (LAST 365 DAYS) ---
        start_date_of_view = today - timedelta(days=364)
        
        if start_date_of_view < habit.start_date:
            start_date_of_view = habit.start_date

        heatmap_data = []
        current_day = start_date_of_view
        
        while current_day <= today:
            status = 1 if current_day in completed_dates else 0
            
            if (today - current_day).days >= 365: 
                break 

            if status == 1:
                css_class = 'completed'
                title_text = 'Completed'
            elif current_day < today:
                css_class = 'missed' # 'Freez' के लिए लाल/ग्रे
                title_text = 'Missed/Freez'
            else:
                css_class = 'pending'
                title_text = 'Pending'
                
            heatmap_data.append({
                'date': current_day,
                'status': status,
                'class': css_class,
                'title': title_text
            })
            current_day += timedelta(days=1)
            
        habit_data.append({
            'name': habit.name,
            'id': habit.id,
            'daily_status': daily_status,
            'heatmap_data': heatmap_data, 
            'start_date': habit.start_date, 
            'goal_status': goal_status_text,
            'progress_percent': progress_percent,
            'pie_chart_data': pie_chart_data,
            'pie_chart_labels': pie_chart_labels,
        })

    return render_template('index.html', habit_data=habit_data, seven_days=seven_days, username=session.get('username'))

# --- Delete and Complete Routes (No Change) ---

@app.route('/delete_habit/<int:habit_id>', methods=['POST'])
def delete_habit(habit_id):
    if 'user_id' not in session:
        flash('Please log in.', 'warning')
        return redirect(url_for('login'))

    user_id = session['user_id']
    habit_to_delete = Habit.query.filter_by(id=habit_id, user_id=user_id).first()

    if habit_to_delete:
        db.session.delete(habit_to_delete)
        db.session.commit()
        flash(f'Habit "{habit_to_delete.name}" has been deleted.', 'success')
    else:
        flash('Habit not found or access denied.', 'danger')

    return redirect(url_for('index'))

@app.route('/complete/<int:habit_id>/<string:date_str>')
def complete_habit(habit_id, date_str):
    if 'user_id' not in session:
        flash('Please log in to track habits.', 'warning')
        return redirect(url_for('login'))
    
    habit = Habit.query.filter_by(id=habit_id, user_id=session['user_id']).first()
    if not habit:
        flash('Habit not found or access denied.', 'danger')
        return redirect(url_for('index'))
        
    try:
        completion_date = date.fromisoformat(date_str)
    except ValueError:
        return redirect(url_for('index'))

    existing_completion = Completion.query.filter_by(
        habit_id=habit_id, date=completion_date
    ).first()

    if existing_completion:
        db.session.delete(existing_completion)
    else:
        new_completion = Completion(habit_id=habit_id, date=completion_date)
        db.session.add(new_completion)
        
    db.session.commit()
    return redirect(url_for('index'))


# --- Main Run Block ---
if __name__ == '__main__':
    with app.app_context():
       
        db.create_all() 
        
    app.run(debug=True)