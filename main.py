import os
from supabase import create_client, Client
import dotenv
from flask import Flask, render_template, request, session, redirect, url_for

dotenv.load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "class-demo-secret-key")

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    print("Error creating Supabase client:", e)
    exit(1)


@app.route('/')
def index():
    try:
        # Get table list by attempting to query information_schema directly
        tables = {}
        
        # Hardcode table names for now - you can add them here
        table_names = ["testtable", "testtable2"]  # Add your table names here
        
        # Fetch data from each table
        for table_name in table_names:
            try:
                table_response = supabase.table(table_name).select("*").execute()
                tables[table_name] = table_response.data
            except Exception as e:
                tables[table_name] = f"Error fetching {table_name}: {e}"
        
        return render_template('index.html', tables=tables)
    except Exception as e:
        return f"Error fetching tables: {e}", 500


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        role = request.form.get('role')
        password = request.form.get('password')
        if role in ['admin', 'student', 'secretary'] and password == role:
            session['user'] = {'role': role}
            return redirect(url_for(role))
        else:
            error = 'Invalid role or password. Try again.'
    return render_template('login.html', error=error)


@app.route('/student')
def student():
    if 'user' not in session or session['user'].get('role') != 'student':
        return redirect(url_for('login'))
    return render_template('student.html', user=session['user'])



@app.route('/secretary')
def secretary():
    if 'user' not in session or session['user'].get('role') != 'secretary':
        return redirect(url_for('login'))
    return render_template('secretary.html', user=session['user'])


@app.route('/admin')
def admin():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template('admin.html', user=session['user'])


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)