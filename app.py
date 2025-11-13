from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_file
from flask_mysqldb import MySQL
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from utils.cloudinary_api import upload_to_cloudinary

app = Flask(__name__)
app.secret_key = 'many random bytes'
#aiven database
load_dotenv()
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_PORT'] = 10985
mysql = MySQL(app)


@app.route('/background')
def background_image():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT data, mimetype FROM images WHERE name = 'cricket.jpg'")
    result = cursor.fetchone()
    if result:
        image_data, mimetype = result
        return Response(image_data, mimetype=mimetype)
    return "Image not found", 404


@app.route('/fav')
def favicon():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT data, mimetype FROM images WHERE name = 'cpl.ico'")
    result = cursor.fetchone()
    if result:
        image_data, mimetype = result
        return Response(image_data, mimetype=mimetype)
    return "Image not found", 404


@app.route('/', methods=['GET'])
@app.route('/<team>', methods=['GET'])
def home(team=None):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM teambalance")
    data = cur.fetchall()
    cur.close()

    team_summary = []

    for row in data:
        selected_team = row[0]  # Extract team name

        # Get opening balance for the selected team
        cur = mysql.connection.cursor()
        cur.execute("SELECT openingbalance FROM teambalance WHERE team = %s", (selected_team,))
        opening_result = cur.fetchone()
        cur.close()
        opening_balance = opening_result[0] if opening_result else 0

        # Get spent amount for the selected team
        cur = mysql.connection.cursor()
        cur.execute("SELECT SUM(Amount) FROM player_list WHERE SoldTo = %s", (selected_team,))
        spent_result = cur.fetchone()
        cur.close()
        spent = spent_result[0] if spent_result[0] is not None else 0

        # Get player count for the selected team
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(playername) FROM player_list WHERE soldto = %s", (selected_team,))
        playercount = cur.fetchone()
        cur.close()
        count = playercount[0] if playercount[0] is not None else 0

        remaining = opening_balance - spent

        team_summary.append({
            'team': selected_team,
            'openingbalance': opening_balance,
            'spentamount': spent,
            'balance': remaining,
            'players': count
        })

        cur = mysql.connection.cursor()
        # Fetch all matches that have a winner
        cur.execute("""
            SELECT `match`, winner, day, time
            FROM match_schedule
            WHERE winner != ''
            ORDER BY day DESC, time DESC
        """)

        all_matches = cur.fetchall()
        team_stats = {}

        for match in all_matches:
            match_name, winner, dat, time = match

            if not match_name:
                continue

            # Normalize team names and split "TeamA vs TeamB"
            if 'vs' not in match_name.lower():
                continue  # skip malformed records

            team_a, team_b = [t.strip() for t in match_name.split('vs')]

            # Initialize stats if team not seen before
            for team in [team_a, team_b]:
                if team not in team_stats:
                    team_stats[team] = {
                        'P': 0, 'W': 0, 'L': 0, 'PTS': 0,
                        'recent': []
                    }

            # Increment matches played
            team_stats[team_a]['P'] += 1
            team_stats[team_b]['P'] += 1

            # Update win/loss/points and recent form
            if winner == team_a:
                team_stats[team_a]['W'] += 1
                team_stats[team_b]['L'] += 1
                team_stats[team_a]['PTS'] += 2
                team_stats[team_a]['recent'].insert(0, 'W')
                team_stats[team_b]['recent'].insert(0, 'L')
            elif winner == team_b:
                team_stats[team_b]['W'] += 1
                team_stats[team_a]['L'] += 1
                team_stats[team_b]['PTS'] += 2
                team_stats[team_b]['recent'].insert(0, 'W')
                team_stats[team_a]['recent'].insert(0, 'L')
            else:
                # No Result (NR)
                team_stats[team_a]['PTS'] += 1
                team_stats[team_b]['PTS'] += 1
                team_stats[team_a]['recent'].insert(0, 'NR')
                team_stats[team_b]['recent'].insert(0, 'NR')

        # Convert team stats into a list for sorting
        leaderboard = []
        for team, stats in team_stats.items():
            # Take last 5 matches for recent form
            recent_form = stats['recent'][:5]

            # If fewer than 5 matches, pad with "-"
            while len(recent_form) < 5:
                recent_form.append('-')

            leaderboard.append({
                'team': team,
                'P': stats['P'],
                'W': stats['W'],
                'L': stats['L'],
                'PTS': stats['PTS'],
                'recent_form': ' '.join(recent_form)
            })

        # Sort by points descending
        leaderboard.sort(key=lambda x: x['PTS'], reverse=True)

        # Add positions
        for i, team in enumerate(leaderboard, start=1):
            team['POS'] = i

        cur.close()


    return render_template(
        "home.html",
        team_summary=team_summary,
        selected_team=team,
        leaderboard=leaderboard
    )


@app.route('/playerList', methods=['GET'])
def playerList():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM player_list")
    data = cur.fetchall()
    cur.close()

    # Convert photo field to string if it's bytes
    cleaned_data = []
    for row in data:
        row = list(row)
        if isinstance(row[6], bytes):
            row[6] = row[6].decode('utf-8')
        cleaned_data.append(row)
    return render_template("playerList.html", player_list=cleaned_data)


@app.route('/addPlayer', methods=['GET'])
def addPlayer():
    return render_template('addplayer.html')


UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Now safely check and create the folder
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])


@app.route('/insert', methods=['POST'])
def insert():
    if request.method == "POST":
        name = request.form['name']
        jerseyNumber = request.form['jerseyNumber']
        jerseySize = request.form['jerseySize']
        role = request.form['role']
        matchFee = request.form['matchFee']
        soldTo = request.form['soldTo']
        photo_file = request.files['photo']
        photo_url = None
        if photo_file and photo_file.filename:
            # Save temporarily to memory
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(photo_file.filename))
            photo_file.save(photo_path)
            photo_url = upload_to_cloudinary(photo_path)
            os.remove(photo_path)  # delete local temp file

        if not photo_url:
            flash("⚠️ Failed to upload photo. Please try again.", "danger")
            return redirect(url_for('addPlayer'))

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO player_list (PlayerName, jerseyNumber, jerseySize, category, payment, photo, soldTo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, jerseyNumber, jerseySize, role, matchFee, photo_url, soldTo))

        mysql.connection.commit()
        cur.close()

        return redirect(url_for('playerList'))


@app.route('/edit-player/<int:serial>', methods=['GET', 'POST'])
def edit_player(serial):
    if request.method == "POST":
        fields = []
        values = []

        # Collect only non-empty fields
        if request.form.get('PlayerName'):
            fields.append("PlayerName=%s")
            values.append(request.form['PlayerName'])

        if request.form.get('jerseyNumber'):
            fields.append("jerseyNumber=%s")
            values.append(request.form['jerseyNumber'])

        if request.form.get('jerseySize'):
            fields.append("jerseySize=%s")
            values.append(request.form['jerseySize'])

        if request.form.get('role'):
            fields.append("category=%s")
            values.append(request.form['role'])

        if request.form.get('matchFee'):
            fields.append("payment=%s")
            values.append(request.form['matchFee'])

        if request.form.get('soldTo'):
            fields.append("soldTo=%s")
            values.append(request.form['soldTo'])

        photo_file = request.files.get('photo')
        if photo_file and photo_file.filename:
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(photo_file.filename))
            photo_file.save(photo_path)
            photo_url = upload_to_cloudinary(photo_path)
            os.remove(photo_path)
            if photo_url:
                fields.append("photo=%s")
                values.append(photo_url)
        else:
            existing_photo = request.form.get('existing_photo')
            if existing_photo:
                fields.append("photo=%s")
                values.append(existing_photo)

        # Only run update if there are fields to update
        if fields:
            query = f"UPDATE player_list SET {', '.join(fields)} WHERE serial=%s"
            values.append(serial)

            cur = mysql.connection.cursor()
            cur.execute(query, tuple(values))
            mysql.connection.commit()
            cur.close()
        else:
            flash("No fields to update.")

        return redirect(url_for('playerList'))

    else:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM player_list WHERE serial = %s", (serial,))
        player = cur.fetchone()
        cur.close()

        if player:
            player = list(player)
            if isinstance(player[6], bytes):
                player[6] = player[6].decode('utf-8')
            return render_template('editplayer.html', player=player)
        else:
            return redirect(url_for('playerList'))


@app.route('/delete-player/<int:serial>')
def delete_player(serial):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM player_list WHERE serial=%s", (serial,))
    mysql.connection.commit()
    return redirect(url_for('playerList'))


@app.route('/team-picture', methods=['GET'])
def team_picture():
    selected_team = request.args.get('team')
    photos = []

    if selected_team:
        cur = mysql.connection.cursor()
        cur.execute("SELECT photo FROM player_list WHERE soldTo = %s", (selected_team,))
        results = cur.fetchall()
        cur.close()
        photos = [row[0].decode('utf-8') if isinstance(row[0], bytes) else row[0] for row in results]

    return render_template('teampic.html', selected_team=selected_team, photos=photos)


@app.route('/update-team', methods=['GET', 'POST'])
@app.route('/update-team/<int:serial>', methods=['GET', 'POST'])
def update_team(serial=None):
    selected_serial = serial or request.form.get('serial') or request.args.get('serial')
    selected_player = None

    # Fetch all players for the dropdown or selection table
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT serial, PlayerName, jerseyNumber, jerseySize, category, payment, photo, soldTo, amount 
        FROM player_list
        ORDER BY serial ASC
    """)
    players = cur.fetchall()

    # If a player is selected, fetch their full details
    if selected_serial:
        cur.execute("SELECT * FROM player_list WHERE serial = %s", (selected_serial,))
        selected_player = cur.fetchone()
        if selected_player:
            selected_player = list(selected_player)
            if isinstance(selected_player[6], bytes):  # Convert photo bytes to string if needed
                selected_player[6] = selected_player[6].decode('utf-8')

    # ---------- Handle Update ----------
    if request.method == 'POST':
        team = request.form.get('team')
        amount = request.form.get('amount')

        if not selected_serial:
            flash("⚠️ Please select a player first.", "warning")
            return redirect(url_for('update_team'))

        if not team:
            flash("⚠️ Team name cannot be empty.", "warning")
            return redirect(url_for('update_team', serial=selected_serial))

        # Perform update
        cur.execute(
            "UPDATE player_list SET soldTo = %s, amount = %s WHERE serial = %s",
            (team, amount, selected_serial)
        )
        mysql.connection.commit()

        flash(f"✅ Player updated successfully — assigned to {team}!", "success")
        cur.close()
        return redirect(url_for('update_team', serial=selected_serial))

    cur.close()
    return render_template(
        'updateTeam.html',
        players=players,
        selected_serial=selected_serial,
        selected_player=selected_player
    )


@app.route('/match-schedule')
def match_schedule():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, `day`, `time`, `match`, `schedule`, 'status',`winner` FROM match_schedule ORDER BY `day`, `time`")

    results = cur.fetchall()
    cur.close()

    matches = [
        {
            'id': row[0],
            'day': row[1],
            'time': row[2],
            'match': row[3],
            'schedule': row[4],
            'winner': row[5]
        }
        for row in results
    ]

    return render_template('schedule.html', matches=matches)


@app.route('/addMatch', methods=['GET'])
def addMatch():
    return render_template('addMatch.html')


@app.route('/add-match', methods=['POST'])
def add_match():
    if request.method == 'POST':
        day = request.form['day']
        time = request.form['time']
        team1 = request.form['team1']
        team2 = request.form['team2']

        if not all([day, time, team1, team2]):
            return redirect(url_for('match_schedule'))  # or your actual schedule route

        match = f"{team1} vs {team2}"
        schedule = f"{day} {time}"

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO match_schedule (`day`, `time`, `match`, `schedule`)
            VALUES (%s, %s, %s, %s)
        """, (day, time, match, schedule))
        mysql.connection.commit()
        cur.close()

        return redirect(url_for('match_schedule'))  # make sure this route exists
    else:
        return redirect(url_for('match_schedule'))


@app.route('/update-winner', methods=['POST'])
def update_winner():
    match_id = request.form.get('match_id')
    winner = request.form.get('winner')

    try:
        match_id = int(match_id)
    except (TypeError, ValueError):
        return redirect(url_for('match_schedule'))

    if not winner:
        return redirect(url_for('match_schedule'))

    cur = mysql.connection.cursor()
    cur.execute("UPDATE match_schedule SET winner = %s WHERE id = %s", (winner, match_id))
    mysql.connection.commit()
    cur.close()

    return redirect(url_for('match_schedule'))


@app.route('/delete-schedule/<int:match_id>',  methods=['POST'])
def delete_schedule(match_id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM match_schedule WHERE id=%s", (match_id,))
    mysql.connection.commit()
    return redirect(url_for('match_schedule'))

#==========================Score Board=================================
# Global match store
match_store = {}
def get_teams_from_match_schedule(match_id):
    cur = mysql.connection.cursor()

    cur.execute("SELECT `match` FROM match_schedule WHERE id = %s", (match_id,))
    row = cur.fetchone()
    cur.close()

    if row and "vs" in row[0]:
        teamA, teamB = [team.strip() for team in row[0].split("vs")]
        return teamA, teamB
    return None, None

def get_players_by_team(team_name):
    cur = mysql.connection.cursor()
    cur.execute("SELECT PlayerName FROM player_list WHERE soldTo = %s", (team_name,))
    rows = cur.fetchall()
    cur.close()
    return [row[0] for row in rows]  # list of player names

def ensure_batsman(name, innings):
    if name not in innings.batsmen:
        innings.batsmen[name] = Batsman(name)
    return innings.batsmen[name]

def ensure_bowler(name, innings):
    if name not in innings.bowlers:
        innings.bowlers[name] = Bowler(name)

@app.route('/scoreboard/<int:match_id>')
def scoreboard(match_id):
    teamA, teamB = get_teams_from_match_schedule(match_id)
    if not teamA or not teamB:
        flash("⚠️ Could not find teams for this match.", "danger")
        return redirect(url_for('match_schedule'))

    # Fetch players for each team
    players_teamA = get_players_by_team(teamA)
    players_teamB = get_players_by_team(teamB)

    # Check if match already exists
    if match_id not in match_store:
        match_store[match_id] = {
            "id": match_id,
            "innings": Innings(batting_team=teamA, bowling_team=teamB),
            "overs_limit": 20
        }

        inns = match_store[match_id]["innings"]

        # ✅ Set initial striker and non-striker from teamA
        if len(players_teamA) >= 2:
            ensure_batsman(players_teamA[0], inns)
            ensure_batsman(players_teamA[1], inns)
            inns.on_strike = players_teamA[0]
            inns.non_strike = players_teamA[1]
        elif len(players_teamA) == 1:
            ensure_batsman(players_teamA[0], inns)
            inns.on_strike = players_teamA[0]
            inns.non_strike = None

        # ✅ Set initial bowler from teamB
        if players_teamB:
            ensure_bowler(players_teamB[0], inns)
            inns.current_bowler = players_teamB[0]

    match_data = match_store[match_id]
    inns = match_data["innings"]
    batsmen = list(inns.batsmen.values())
    bowlers = list(inns.bowlers.values())

    return render_template(
        "scoreboard.html",
        match=match_data,
        inns=inns,
        batsmen=batsmen,
        bowlers=bowlers,
        players_teamA=players_teamA,
        players_teamB=players_teamB
    )

@app.route("/set_striker", methods=["POST"])
def set_striker():
    name = request.form.get("name")
    match_id = int(request.form.get("match_id"))
    inns = match_store[match_id]["innings"]
    ensure_batsman(name, inns)
    inns.on_strike = name
    return redirect(url_for("scoreboard", match_id=match_id))

@app.route("/set_non_striker", methods=["POST"])
def set_non_striker():
    name = request.form.get("name")
    match_id = int(request.form.get("match_id"))
    inns = match_store[match_id]["innings"]
    ensure_batsman(name, inns)
    inns.non_strike = name
    return redirect(url_for("scoreboard", match_id=match_id))

@app.route("/set_bowler", methods=["POST"])
def set_bowler():
    name = request.form.get("name")
    match_id = int(request.form.get("match_id"))
    print(match_id)
    inns = match_store[match_id]["innings"]
    ensure_bowler(name, inns)
    inns.current_bowler = name
    return redirect(url_for("scoreboard", match_id=match_id))

@app.route("/update_ball", methods=["POST"])
def update_ball():
    match_id = int(request.form.get("match_id"))
    inns = match_store[match_id]["innings"]

    runs_bat = int(request.form.get("runs_bat", 0))
    wd = int(request.form.get("extras_wd", 0))
    nb = int(request.form.get("extras_nb", 0))
    lb = int(request.form.get("extras_lb", 0))
    b = int(request.form.get("extras_b", 0))
    wicket = bool(request.form.get("wicket"))
    dismissal_desc = request.form.get("dismissal_desc") or None

    extras = {}
    if wd: extras["wd"] = wd
    if nb: extras["nb"] = nb
    if lb: extras["lb"] = lb
    if b:  extras["b"] = b

    apply_ball(inns, runs_bat=runs_bat, extras=extras, wicket=wicket, dismissal_desc=dismissal_desc)
    return redirect(url_for("scoreboard", match_id=match_id))

def apply_ball(innings, runs_bat=0, extras=None, wicket=False, dismissal_desc=None, switch_strike_on_odd=True):
    """
    Apply a ball to the given innings.
    extras: dict like {"wd":1} or {"nb":1, "lb":1} etc.
    wicket: bool (only one wicket per ball in this simple model)
    runs_bat: runs off the bat (0-6)
    """
    inns = innings
    extras = extras or {}

    striker = inns.batsmen[inns.on_strike]
    bowler = inns.bowlers[inns.current_bowler]

    # Determine if the ball counts as legal (wd and nb do not count as legal deliveries)
    is_legal = ("wd" not in extras) and ("nb" not in extras)

    # Compute total runs for team this ball
    total_runs = runs_bat + sum(extras.values())

    # Update team total
    inns.total += total_runs

    # Update batsman stats (only runs off bat count)
    if is_legal:
        striker.balls += 1
    striker.runs += runs_bat
    if runs_bat == 4:
        striker.fours += 1
    elif runs_bat == 6:
        striker.sixes += 1

    # Update bowler figures
    bowler.runs_conceded += total_runs
    if is_legal:
        bowler.overs_bowled_balls += 1
        bowler.current_over_runs += total_runs

    # Wicket handling
    if wicket:
        inns.wickets += 1
        bowler.wickets += 1
        # If dismissal_desc is just the batsman's name, ignore it
        if dismissal_desc and dismissal_desc.strip().lower() == striker.name.lower():
            striker.out_desc = f"b {bowler.name}"
        else:
            striker.out_desc = dismissal_desc or f"b {bowler.name}"

    # Strike rotation
    rotate_strike = False
    odd_runs_trigger = (runs_bat % 2 == 1)
    odd_extras_trigger = ((extras.get("lb", 0) + extras.get("b", 0)) % 2 == 1)
    if switch_strike_on_odd and is_legal and (odd_runs_trigger or odd_extras_trigger):
        rotate_strike = True

    # End of over: if legal ball was 6th in over, rotate strike and reset over runs
    over_idx = inns.overs_balls // 6
    ball_no_in_over = (inns.overs_balls % 6) + (1 if is_legal else 0)
    desc = build_ball_desc(runs_bat, extras, wicket)
    event = BallEvent(over_num=over_idx,
                      ball_num=ball_no_in_over,
                      desc=desc,
                      runs=total_runs,
                      extras=extras,
                      wicket=wicket)

    inns.timeline.append(event)
    inns.over_events.setdefault(over_idx, []).append(event)

    if is_legal:
        inns.overs_balls += 1

    # If over completes
    if inns.overs_balls % 6 == 0 and inns.overs_balls != 0:
        if bowler.current_over_runs == 0:
            bowler.maidens += 1
        bowler.current_over_runs = 0
        rotate_strike = not rotate_strike

    if rotate_strike:
        inns.on_strike, inns.non_strike = inns.non_strike, inns.on_strike

#==============Additional=================
class Batsman:
    def __init__(self, name):
        self.name = name
        self.runs = 0
        self.balls = 0
        self.fours = 0
        self.sixes = 0
        self.out_desc = None

    @property
    def strike_rate(self):
        return round((self.runs / self.balls) * 100, 2) if self.balls else 0.0

class Bowler:
    def __init__(self, name):
        self.name = name
        self.overs_bowled_balls = 0  # track balls for partial overs
        self.runs_conceded = 0
        self.wickets = 0
        self.maidens = 0
        self.current_over_runs = 0
    @property
    def overs(self):
        return f"{self.overs_bowled_balls // 6}.{self.overs_bowled_balls % 6}"
    @property
    def economy(self):
        overs_decimal = self.overs_bowled_balls / 6 if self.overs_bowled_balls else 0
        return round(self.runs_conceded / overs_decimal, 2) if overs_decimal else 0.0

class BallEvent:
    def __init__(self, over_num, ball_num, desc, runs, extras=None, wicket=False):
        self.over_num = over_num     # int (over index)
        self.ball_num = ball_num     # 1..6 or incremented for extra deliveries
        self.desc = desc             # short string for UI (e.g., "4", "W", "1lb", "Wd")
        self.runs = runs             # total runs added to team
        self.extras = extras or {}   # e.g., {"wd":1}, {"lb":1}, {"nb":1,"bat":2}
        self.wicket = wicket

class Innings:
    def __init__(self, batting_team, bowling_team):
        self.batting_team = batting_team
        self.bowling_team = bowling_team
        self.total = 0
        self.wickets = 0
        self.overs_balls = 0  # total legal balls bowled
        self.batsmen = {}     # name -> Batsman
        self.bowlers = {}     # name -> Bowler
        self.on_strike = None
        self.non_strike = None
        self.current_bowler = None
        self.timeline = []    # list[BallEvent]
        self.over_events = {} # over_idx -> list[BallEvent]

    @property
    def overs(self):
        return f"{self.overs_balls // 6}.{self.overs_balls % 6}"

# --- In-memory match state (replace with DB later) ---
match = {
    "innings": Innings(batting_team="India", bowling_team="Australia"),
    "overs_limit": 20
}

# --- Core update logic ---


def build_ball_desc(runs_bat, extras, wicket):
    if wicket:
        return "W"
    parts = []
    if "wd" in extras:
        parts.append(f"Wd{extras['wd']}")
    if "nb" in extras:
        nb = extras["nb"]
        bat_note = f"+{runs_bat}" if runs_bat else ""
        parts.append(f"Nb{nb}{bat_note}")
    if "lb" in extras:
        parts.append(f"LB{extras['lb']}")
    if "b" in extras:
        parts.append(f"B{extras['b']}")
    if runs_bat and "nb" not in extras:
        parts.append(str(runs_bat))
    return "+".join(parts) if parts else "0"


if __name__ == "__main__":
    app.run(debug=True)