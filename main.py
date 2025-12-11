import os
from datetime import datetime
from supabase import create_client, Client
import dotenv
from flask import Flask, render_template, request, session, redirect, url_for

dotenv.load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "class-demo-secret-key")


@app.template_filter('pretty_datetime')
def pretty_datetime(value: str) -> str:
    """Format ISO-ish datetime strings into a friendlier display for templates.

    Keeps original value on parse errors so we never break pages.
    """
    if not value:
        return ''
    try:
        # Handle values like '2025-12-10T09:00', '2025-12-10 09:00', or with seconds/timezone
        text = str(value).replace(' ', 'T')
        # Trim to seconds to keep fromisoformat happy even if timezone present
        if len(text) > 19:
            text = text[:19]
        dt = datetime.fromisoformat(text)
        return dt.strftime('%b %d, %Y %I:%M %p')  # e.g., Dec 10, 2025 09:00 AM
    except Exception:
        return str(value)

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
        tables = {}
        # Show a summary of key tables in the schema
        table_names = [
            "Building",
            "Department",
            "Course",
            "Room",
            "Section",
            "Equipment Type",
            "Room Equipment",
            "Request Equipment",
            "Room Assignment",
            "Blackout Hours",
            "Class Request",
        ]
        
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
        
        # Check credentials: admin/admin, secretary/secretary
        valid_credentials = {
            'admin': 'admin',
            'secretary': 'secretary'
        }
        
        if role in valid_credentials and password == valid_credentials[role]:
            session['user'] = {'role': role}
            return redirect(url_for(role))
        else:
            error = 'Invalid role or password. Try again.'
    return render_template('login.html', error=error)


@app.route('/student')
def student():
    # Public search interface: no login required, read-only
    class_number = request.args.get('class_number', '').strip()
    building_id = request.args.get('building_id', '').strip()
    dept_id = request.args.get('dept_id', '').strip()
    time_filter = request.args.get('time', '').strip()

    # Load lookup tables
    buildings = []
    departments = []
    try:
        buildings = supabase.table('Building').select('*').execute().data
    except Exception as e:
        print('Error fetching buildings for student search:', e)
    try:
        departments = supabase.table('Department').select('*').execute().data
    except Exception as e:
        print('Error fetching departments for student search:', e)

    # Load core scheduling data and join in Python
    sections = []
    courses = []
    room_assignments = []
    rooms = []
    try:
        sections = supabase.table('Section').select('*').execute().data
    except Exception as e:
        print('Error fetching sections:', e)
    try:
        courses = supabase.table('Course').select('*').execute().data
    except Exception as e:
        print('Error fetching courses:', e)
    try:
        room_assignments = supabase.table('Room Assignment').select('*').execute().data
    except Exception as e:
        print('Error fetching room assignments:', e)
    try:
        rooms = supabase.table('Room').select('*').execute().data
    except Exception as e:
        print('Error fetching rooms:', e)

    section_by_id = {s.get('section_id'): s for s in sections}
    course_by_id = {c.get('course_id'): c for c in courses}
    room_by_id = {r.get('room_id'): r for r in rooms}

    # Map departments by their primary key; your schema uses department_id
    dept_by_id = {}
    for d in departments:
        dept_key = d.get('department_id') or d.get('dept_id') or d.get('id')
        if dept_key is not None:
            dept_by_id[dept_key] = d

    results = []
    # Track which **courses** actually have room assignments so we can
    # build a dropdown of available classes (by course) for students to search.
    available_courses = {}
    # Helper to parse stored datetimes down to minutes
    def _to_minute_dt(value: str):
        if not value:
            return None
        text = str(value).replace(' ', 'T')
        trimmed = text[:16]
        try:
            return datetime.fromisoformat(trimmed)
        except Exception as parse_err:
            print('Error parsing datetime in student search:', value, parse_err)
            return None

    for ra in room_assignments:
        s = section_by_id.get(ra.get('section_id'))
        if not s:
            continue
        # Course lookup with tolerant key handling
        course_id_val = s.get('course_id') or s.get('courseID') or s.get('course')
        c = course_by_id.get(course_id_val) if course_id_val is not None else None
        # Department is optional for displaying results; try best-effort lookup
        dept_id_val = None
        if c:
            # Your Course table likely stores the FK as dept_id
            dept_id_val = (
                c.get('dept_id')
                or c.get('department_id')
                or c.get('dept')
            )
        d = dept_by_id.get(dept_id_val) if dept_id_val is not None else None
        r = room_by_id.get(ra.get('room_id'))
        # Require a valid course and room assignment; department is optional
        if not (c and r):
            continue

        # Friendly fields with fallbacks so we don't end up with a bunch of None values
        # Your Course table uses course_id and name
        course_id_out = c.get('course_id') or c.get('id')
        course_name_out = c.get('name') or c.get('course_name')
        dept_id_out = dept_id_val
        dept_name_out = None
        if d:
            # Your Department schema uses `name` for the department name
            dept_name_out = (
                d.get('name')
                or d.get('dept_name')
                or d.get('department_name')
            )

        section_type_out = s.get('section_type') or s.get('type')
        section_num_out = s.get('section_num') or s.get('number') or s.get('sec_num')

        row = {
            'course_id': course_id_out,
            'course_name': course_name_out,
            'dept_id': dept_id_out,
            'dept_name': dept_name_out,
            'section_id': s.get('section_id'),
            'section_type': section_type_out,
            'section_num': section_num_out,
            'building_id': r.get('building_id'),
            'room_num': r.get('room_num'),
            'room_type': r.get('room_type'),
            'max_capacity': r.get('max_capacity'),
            # Room Assignment table uses 'start' and 'end' columns
            'assign_start': ra.get('start'),
            'assign_end': ra.get('end'),
        }

        # Apply filters
        # Class filter uses course_id so students choose a specific class (e.g., COMP 440)
        if class_number and str(row.get('course_id')) != class_number:
            continue
        if building_id and str(row.get('building_id')) != building_id:
            continue
        if dept_id and str(row.get('dept_id')) != dept_id:
            continue
        if time_filter:
            # Expect HH:MM from a time input; if parsing fails, fall back to simple substring match
            from datetime import time as _time_cls  # local alias to avoid confusion
            req_time = None
            try:
                req_time = datetime.strptime(time_filter, '%H:%M').time()
            except Exception:
                req_time = None

            if req_time:
                st = _to_minute_dt(row.get('assign_start'))
                et = _to_minute_dt(row.get('assign_end'))
                if not st or not et:
                    continue
                # Match if requested time falls within [start, end)
                if not (st.time() <= req_time < et.time()):
                    continue
            else:
                start_str = str(row.get('assign_start') or '')
                end_str = str(row.get('assign_end') or '')
                if time_filter not in start_str and time_filter not in end_str:
                    continue

        results.append(row)

        # Track which courses have at least one room assignment
        course_key = row.get('course_id')
        if course_key not in available_courses:
            available_courses[course_key] = {
                'course_id': row.get('course_id'),
                'course_name': row.get('course_name'),
                'dept_id': row.get('dept_id'),
                'dept_name': row.get('dept_name'),
            }

    # Student has no session-based identity; pass user=None
    # Sort available classes by department and course name for a tidy dropdown
    available_classes = sorted(
        available_courses.values(),
        key=lambda c: (
            str(c.get('dept_id') or ''),
            str(c.get('course_name') or ''),
        ),
    )

    return render_template(
        'student.html',
        user=None,
        buildings=buildings,
        departments=departments,
        available_classes=available_classes,
        results=results,
        class_number=class_number,
        selected_building=building_id,
        selected_dept=dept_id,
        time_filter=time_filter,
    )



@app.route('/secretary')
def secretary():
    if 'user' not in session or session['user'].get('role') != 'secretary':
        return redirect(url_for('login'))

    class_requests = []
    room_assignments = []
    rooms = []
    sections = []
    request_equipment = []
    equipment_types = []
    try:
        class_requests = supabase.table('Class Request').select('*').execute().data
    except Exception as e:
        print('Error fetching class requests:', e)
    try:
        room_assignments = supabase.table('Room Assignment').select('*').execute().data
    except Exception as e:
        print('Error fetching room assignments:', e)
    try:
        rooms = supabase.table('Room').select('*').execute().data
    except Exception as e:
        print('Error fetching rooms:', e)
    try:
        sections = supabase.table('Section').select('*').execute().data
    except Exception as e:
        print('Error fetching sections:', e)

    try:
        request_equipment = supabase.table('Request Equipment').select('*').execute().data
    except Exception as e:
        print('Error fetching request equipment:', e)

    try:
        equipment_types = supabase.table('Equipment Type').select('*').execute().data
    except Exception as e:
        print('Error fetching equipment types (secretary):', e)

    # Map equipment requests by class request id for easy lookup in template
    request_equipment_by_request = {
        re.get('request_id'): re for re in request_equipment
    }

    # Simple mapping from equipment id to name (best-effort; falls back to id)
    equipment_name_by_id = {
        et.get('equip_id'): et.get('name') or et.get('eq_description') or et.get('description') or ''
        for et in equipment_types
    }

    return render_template(
        'secretary.html',
        user=session['user'],
        class_requests=class_requests,
        room_assignments=room_assignments,
        rooms=rooms,
        sections=sections,
        request_equipment_by_request=request_equipment_by_request,
        equipment_types=equipment_types,
        equipment_name_by_id=equipment_name_by_id,
    )


@app.route('/secretary/request', methods=['POST'])
def create_class_request():
    if 'user' not in session or session['user'].get('role') != 'secretary':
        return redirect(url_for('login'))

    section_id = request.form.get('section_id')
    requester = request.form.get('requester')
    requested_start = request.form.get('requested_start')
    requested_end = request.form.get('requested_end')
    preferred_room_id = request.form.get('preferred_room') or None
    equipment_id = request.form.get('equipment_id') or None
    quantity_raw = request.form.get('quantity') or None

    preferred_room_text = None
    if preferred_room_id:
        try:
            room_resp = supabase.table('Room').select('building_id, room_num').eq('room_id', int(preferred_room_id)).execute()
            if room_resp.data:
                room = room_resp.data[0]
                preferred_room_text = f"{room.get('building_id')} {room.get('room_num')}"
        except Exception as e:
            print('Error looking up preferred room for insert:', e)

    new_request_id = None
    try:
        payload = {
            'section_id': int(section_id) if section_id else None,
            'requester': requester,
            'requested_start': requested_start,
            'requested_end': requested_end,
            'preferred_room': preferred_room_text,
            'status': 'pending',
        }
        resp = supabase.table('Class Request').insert(payload).execute()
        if resp.data:
            new_request_id = resp.data[0].get('request_id')
    except Exception as e:
        print('Error inserting class request:', e)

    # If equipment was selected, create a linked equipment request row
    if new_request_id and equipment_id:
        try:
            qty = int(quantity_raw) if quantity_raw else 1
        except ValueError:
            qty = 1

        try:
            eq_payload = {
                'request_id': new_request_id,
                'room_id': int(preferred_room_id) if preferred_room_id else None,
                'equip_id': int(equipment_id),
                'quantity': qty,
            }
            supabase.table('Request Equipment').insert(eq_payload).execute()
        except Exception as e_eq:
            print('Error inserting request equipment:', e_eq)

    return redirect(url_for('secretary'))


@app.route('/secretary/request/<int:request_id>', methods=['POST'])
def update_class_request(request_id: int):
    if 'user' not in session or session['user'].get('role') != 'secretary':
        return redirect(url_for('login'))

    requested_start = request.form.get('requested_start')
    requested_end = request.form.get('requested_end')
    preferred_room_id = request.form.get('preferred_room') or None

    preferred_room_text = None
    if preferred_room_id:
        try:
            room_resp = supabase.table('Room').select('building_id, room_num').eq('room_id', int(preferred_room_id)).execute()
            if room_resp.data:
                room = room_resp.data[0]
                preferred_room_text = f"{room.get('building_id')} {room.get('room_num')}"
        except Exception as e:
            print('Error looking up preferred room for update:', e)

    update_data = {
        'requested_start': requested_start,
        'requested_end': requested_end,
        'preferred_room': preferred_room_text,
    }

    try:
        supabase.table('Class Request').update(update_data).eq('request_id', request_id).execute()
    except Exception as e:
        print('Error updating class request:', e)

    return redirect(url_for('secretary'))


@app.route('/admin')
def admin():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))

    error = request.args.get('error')

    buildings = []
    departments = []
    courses = []
    rooms = []
    equipment_types = []
    class_requests = []
    room_assignments = []
    request_equipment = []
    try:
        buildings = supabase.table('Building').select('*').execute().data
    except Exception as e:
        print('Error fetching buildings:', e)
    try:
        departments = supabase.table('Department').select('*').execute().data
    except Exception as e:
        print('Error fetching departments:', e)
    try:
        courses = supabase.table('Course').select('*').execute().data
    except Exception as e:
        print('Error fetching courses:', e)
    try:
        rooms = supabase.table('Room').select('*').execute().data
    except Exception as e:
        print('Error fetching rooms:', e)
    try:
        equipment_types = supabase.table('Equipment Type').select('*').execute().data
    except Exception as e:
        print('Error fetching equipment types:', e)

    try:
        class_requests = supabase.table('Class Request').select('*').execute().data
    except Exception as e:
        print('Error fetching class requests (admin):', e)
    try:
        room_assignments = supabase.table('Room Assignment').select('*').execute().data
    except Exception as e:
        print('Error fetching room assignments (admin):', e)

    try:
        request_equipment = supabase.table('Request Equipment').select('*').execute().data
    except Exception as e:
        print('Error fetching request equipment (admin):', e)

    # Map equipment requests by class request id and names for display
    request_equipment_by_request = {re.get('request_id'): re for re in request_equipment}
    equipment_name_by_id = {
        et.get('equip_id'): et.get('name') or et.get('eq_description') or et.get('description') or ''
        for et in equipment_types
    }

    return render_template(
        'admin.html',
        user=session['user'],
        error=error,
        buildings=buildings,
        departments=departments,
        courses=courses,
        rooms=rooms,
        equipment_types=equipment_types,
        class_requests=class_requests,
        room_assignments=room_assignments,
        request_equipment_by_request=request_equipment_by_request,
        equipment_name_by_id=equipment_name_by_id,
    )


@app.route('/admin/assign/<int:request_id>', methods=['POST'])
def accept_request(request_id: int):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))

    room_id = request.form.get('room_id')
    if not room_id:
        return redirect(url_for('admin'))

    try:
        resp = supabase.table('Class Request').select('*').eq('request_id', request_id).execute()
        if not resp.data:
            return redirect(url_for('admin'))
        req = resp.data[0]

        # Check for time conflict in the same room.
        # Normalize timestamps to minute precision (YYYY-MM-DDTHH:MM) so
        # HTML datetime-local values and Supabase stored values align.
        new_start_raw = req.get('requested_start')
        new_end_raw = req.get('requested_end')

        def _to_minute_dt(value: str):
            if not value:
                return None
            # Take only "YYYY-MM-DDTHH:MM" part
            trimmed = value[:16]
            try:
                return datetime.fromisoformat(trimmed)
            except Exception as parse_err:
                print('Error parsing datetime for conflict check:', value, parse_err)
                return None

        ns = _to_minute_dt(new_start_raw)
        ne = _to_minute_dt(new_end_raw)

        if ns and ne:
            # Check for conflicts with existing room assignments
            try:
                existing_resp = supabase.table('Room Assignment').select('start,end').eq('room_id', int(room_id)).execute()
                for ra in existing_resp.data:
                    exist_start_raw = ra.get('start')
                    exist_end_raw = ra.get('end')
                    es = _to_minute_dt(exist_start_raw)
                    ee = _to_minute_dt(exist_end_raw)
                    if not es or not ee:
                        continue

                    # Overlap if new_start < existing_end and existing_start < new_end
                    if ns < ee and es < ne:
                        return redirect(url_for('admin', error='That room is already booked for this time slot. Please choose another room.'))
            except Exception as e_conflict:
                print('Error checking for room conflicts:', e_conflict)

            # Also check for conflicts with blackout hours for this room
            try:
                blackout_resp = supabase.table('Blackout Hours').select('start,end').eq('room_id', int(room_id)).execute()
                for bo in blackout_resp.data:
                    bo_start_raw = bo.get('start')
                    bo_end_raw = bo.get('end')
                    bs = _to_minute_dt(bo_start_raw)
                    be = _to_minute_dt(bo_end_raw)
                    if not bs or not be:
                        continue

                    if ns < be and bs < ne:
                        return redirect(url_for('admin', error='That room is unavailable during the requested time due to blackout hours.'))
            except Exception as e_blackout:
                print('Error checking blackout hours:', e_blackout)

        payload = {
            'request_id': request_id,
            'section_id': req.get('section_id'),
            'room_id': int(room_id),
            'start': req.get('requested_start'),
            'end': req.get('requested_end'),
            'status': 'assigned',
        }
        supabase.table('Room Assignment').insert(payload).execute()

        # If there is a linked equipment request, apply it to Room Equipment for this room
        try:
            eq_resp = supabase.table('Request Equipment').select('*').eq('request_id', request_id).execute()
            if eq_resp.data:
                eq_row = eq_resp.data[0]
                room_eq_payload = {
                    'room_id': int(room_id),
                    'equip_id': eq_row.get('equip_id'),
                    'quantity': eq_row.get('quantity') or 1,
                }
                supabase.table('Room Equipment').insert(room_eq_payload).execute()
        except Exception as e_eq_apply:
            print('Error applying room equipment for accepted request:', e_eq_apply)

        # Also mark the class request as assigned
        try:
            supabase.table('Class Request').update({'status': 'assigned'}).eq('request_id', request_id).execute()
        except Exception as e_update:
            print('Error updating class request status:', e_update)
    except Exception as e:
        print('Error accepting class request:', e)

    return redirect(url_for('admin'))


@app.route('/admin/suggest_room/<int:request_id>', methods=['POST'])
def suggest_room(request_id: int):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))

    try:
        # Load the class request we are trying to schedule
        resp = supabase.table('Class Request').select('*').eq('request_id', request_id).execute()
        if not resp.data:
            return redirect(url_for('admin', error='Class request not found.'))
        req = resp.data[0]

        new_start_raw = req.get('requested_start')
        new_end_raw = req.get('requested_end')

        def _to_minute_dt(value: str):
            if not value:
                return None
            trimmed = value[:16]
            try:
                return datetime.fromisoformat(trimmed)
            except Exception as parse_err:
                print('Error parsing datetime for room suggestion:', value, parse_err)
                return None

        ns = _to_minute_dt(new_start_raw)
        ne = _to_minute_dt(new_end_raw)
        if not (ns and ne):
            return redirect(url_for('admin', error='Request is missing valid start/end times.'))

        # Load all rooms and prefer ones in the same building as the preferred_room text, if any
        rooms_resp = supabase.table('Room').select('*').execute()
        rooms = rooms_resp.data or []

        preferred_room_text = req.get('preferred_room') or ''
        preferred_building = preferred_room_text.split()[0] if preferred_room_text else None

        def room_sort_key(r):
            b_id = str(r.get('building_id') or '')
            same_building = 0 if preferred_building and b_id == preferred_building else 1
            return (same_building, b_id, str(r.get('room_num') or ''))

        rooms_sorted = sorted(rooms, key=room_sort_key)

        def is_room_free(room_id: int) -> bool:
            # Check existing assignments
            try:
                existing_resp = supabase.table('Room Assignment').select('start,end').eq('room_id', room_id).execute()
                for ra in existing_resp.data:
                    es = _to_minute_dt(ra.get('start'))
                    ee = _to_minute_dt(ra.get('end'))
                    if not es or not ee:
                        continue
                    if ns < ee and es < ne:
                        return False
            except Exception as e_conflict:
                print('Error checking room assignments for suggestion:', e_conflict)
                return False

            # Check blackout hours
            try:
                blackout_resp = supabase.table('Blackout Hours').select('start,end').eq('room_id', room_id).execute()
                for bo in blackout_resp.data:
                    bs = _to_minute_dt(bo.get('start'))
                    be = _to_minute_dt(bo.get('end'))
                    if not bs or not be:
                        continue
                    if ns < be and bs < ne:
                        return False
            except Exception as e_blackout:
                print('Error checking blackout hours for suggestion:', e_blackout)
                return False

            return True

        suggested_room = None
        for r in rooms_sorted:
            rid = r.get('room_id')
            if rid is None:
                continue
            try:
                rid_int = int(rid)
            except Exception:
                continue
            if is_room_free(rid_int):
                suggested_room = r
                break

        if not suggested_room:
            return redirect(url_for('admin', error='No available room found for this time slot.'))

        # Auto-create the room assignment for the suggested room
        try:
            room_id = int(suggested_room.get('room_id'))
        except Exception:
            return redirect(url_for('admin', error='Error determining suggested room id.'))

        payload = {
            'request_id': request_id,
            'section_id': req.get('section_id'),
            'room_id': room_id,
            'start': req.get('requested_start'),
            'end': req.get('requested_end'),
            'status': 'assigned',
        }
        try:
            supabase.table('Room Assignment').insert(payload).execute()
        except Exception as e_insert:
            print('Error inserting suggested room assignment:', e_insert)
            return redirect(url_for('admin', error='Failed to create room assignment for suggested room.'))

        # Apply any requested equipment to Room Equipment
        try:
            eq_resp = supabase.table('Request Equipment').select('*').eq('request_id', request_id).execute()
            if eq_resp.data:
                eq_row = eq_resp.data[0]
                room_eq_payload = {
                    'room_id': room_id,
                    'equip_id': eq_row.get('equip_id'),
                    'quantity': eq_row.get('quantity') or 1,
                }
                supabase.table('Room Equipment').insert(room_eq_payload).execute()
        except Exception as e_eq_apply:
            print('Error applying room equipment for suggested room:', e_eq_apply)

        # Mark the class request as assigned
        try:
            supabase.table('Class Request').update({'status': 'assigned'}).eq('request_id', request_id).execute()
        except Exception as e_update:
            print('Error updating class request status after suggestion:', e_update)

        building_label = suggested_room.get('building_id')
        room_label = suggested_room.get('room_num')
        msg = f"Request {request_id} assigned to suggested room {building_label} {room_label}."
        return redirect(url_for('admin', error=msg))

    except Exception as e:
        print('Error suggesting room:', e)
        return redirect(url_for('admin', error='Unexpected error while suggesting room.'))


@app.route('/admin/assignment/<int:assignment_id>', methods=['POST'])
def update_assignment(assignment_id: int):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))

    new_room_id = request.form.get('room_id')
    new_start_raw = request.form.get('start')
    new_end_raw = request.form.get('end')

    if not (new_room_id and new_start_raw and new_end_raw):
        return redirect(url_for('admin', error='Room, start, and end are required to update an assignment.'))

    def _to_minute_dt(value: str):
        if not value:
            return None
        trimmed = value[:16]
        try:
            return datetime.fromisoformat(trimmed)
        except Exception as parse_err:
            print('Error parsing datetime for assignment update:', value, parse_err)
            return None

    ns = _to_minute_dt(new_start_raw)
    ne = _to_minute_dt(new_end_raw)
    if not (ns and ne):
        return redirect(url_for('admin', error='Invalid start or end time for assignment update.'))

    try:
        # Check for conflicts with other assignments for this room (exclude this assignment)
        existing_resp = supabase.table('Room Assignment').select('assignment_id, start, end').eq('room_id', int(new_room_id)).execute()
        for ra in existing_resp.data:
            if ra.get('assignment_id') == assignment_id or ra.get('assign_id') == assignment_id:
                continue
            es = _to_minute_dt(ra.get('start'))
            ee = _to_minute_dt(ra.get('end'))
            if not es or not ee:
                continue
            if ns < ee and es < ne:
                return redirect(url_for('admin', error='Updated time conflicts with another assignment in that room.'))

        # Check blackout hours for the new room/time
        blackout_resp = supabase.table('Blackout Hours').select('start,end').eq('room_id', int(new_room_id)).execute()
        for bo in blackout_resp.data:
            bs = _to_minute_dt(bo.get('start'))
            be = _to_minute_dt(bo.get('end'))
            if not bs or not be:
                continue
            if ns < be and bs < ne:
                return redirect(url_for('admin', error='Updated time falls within blackout hours for that room.'))

        # If we reach here, it is safe to update the assignment
        update_payload = {
            'room_id': int(new_room_id),
            'start': new_start_raw,
            'end': new_end_raw,
        }
        supabase.table('Room Assignment').update(update_payload).eq('assignment_id', assignment_id).execute()

    except Exception as e:
        print('Error updating room assignment:', e)
        return redirect(url_for('admin', error='Unexpected error while updating assignment.'))

    return redirect(url_for('admin'))


@app.route('/admin/blackout', methods=['POST'])
def add_blackout():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))

    room_id = request.form.get('room_id')
    start = request.form.get('blackout_start')
    end = request.form.get('blackout_end')
    reason = request.form.get('reason')

    try:
        payload = {
            'room_id': int(room_id) if room_id else None,
            # Table uses columns named start and end
            'start': start,
            'end': end,
            'reason': reason,
        }
        supabase.table('Blackout Hours').insert(payload).execute()
    except Exception as e:
        print('Error inserting blackout hours:', e)

    return redirect(url_for('admin'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)