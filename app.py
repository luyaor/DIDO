import sys
import os
from datetime import datetime

from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, g, abort, current_app
from flask_login import LoginManager, UserMixin, AnonymousUserMixin, logout_user, login_user, login_required, current_user
from flask_pymongo import PyMongo
from flask_github import GitHub

from util import wordext
import nlp_model

app = Flask(__name__)

app.config["MONGO_URI"] = "mongodb://localhost:27017/dido_db?connect=false"
app.config["SECRET_KEY"] = "build_it_better"

app.config['GITHUB_CLIENT_ID'] = 'b32ca6bbebe2a91ed71d'
app.config['GITHUB_CLIENT_SECRET'] = 'fc501d59ec54c31797e53bf583cca4e42f80c9cc'


github = GitHub(app)

login_manager = LoginManager(app)

mongo = PyMongo(app)

debug_flag = True

# -------------------------------------------------------------------------------------
# User model, Login & Logout

class User(UserMixin):
    def __init__(self, username, github_access_token):
        self.id = username
        self.github_access_token = github_access_token

    def is_admin(self):
        return self.id == 'FancyCoder0'
    
class AnonymousUser(AnonymousUserMixin):
    def is_admin(self):
        return False

login_manager.anonymous_user = AnonymousUser
def admin_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return inner

@login_manager.user_loader
def load_user(username):
    user = mongo.db.github_user.find_one({'_id': username})
    return User(user['_id'], user['github_access_token'])

@github.access_token_getter
def token_getter():
    if current_user.is_authenticated:
        return current_user.github_access_token
    else:
        return g.get('github_access_token', None)

@app.route('/login')
def login():
    return github.authorize()

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return 'Logout!'

@app.route('/github-callback')
@github.authorized_handler
def authorized(oauth_token):
    next_url = request.args.get('next') or url_for('index')
    if oauth_token is None:
        flash("Authorization failed.")
        return redirect(next_url)
    
    g.github_access_token = oauth_token    
    github_user_info = github.get('user')
    github_username = github_user_info["login"]
        
    user = mongo.db.github_user.find_one({'_id': github_username})
    if user is None:
        mongo.db.github_user.save({'_id': github_username, 'github_access_token': oauth_token})
    
    login_user(User(github_username, oauth_token))
    return redirect(next_url)

# -------------------------------------------------------------------------------------


model = None


def get_raw_issues(repo, option='all'):

    def update_issue(raw_issues):
        for issue in raw_issues:
            _id = repo + issue['number']
            data = {'repo': repo, 'num': issue['number'], 'num1_data': issue}
            mongo.db.issue.update({'_id': _id}, {'$set': data}, upsert=True)

    if option == 'only_open':
        open_issues = api.request('GET', 'repos/%s/%ss?state=open' % (repo, 'issue'), True)
        mongo.db.issue_list.update({'_id': repo}, {'$set': {'open_issues': open_issues,}}, upsert=True)
        update_issue(open_issues)
        return open_issues

    r = mongo.db.issue_list.find_one({'_id': repo})
    
    if (r is None) or ('updated_time' not in r) or ((datetime.utcnow() - r['updated_time']).days >= 7) or ('refresh' in option):
        open_issues = api.request('GET', 'repos/%s/%ss?state=open' % (repo, 'issue'), True)
        mongo.db.issue_list.update({'_id': repo}, {'$set': {'open_issues': open_issues,}}, upsert=True)
        update_issue(open_issues)
        closed_issues = api.request('GET', 'repos/%s/%ss?state=closed' % (repo, 'issue'), True)
        mongo.db.issue_list.update({'_id': repo}, {'$set': {'closed_issues': closed_issues,}}, upsert=True)
        update_issue(closed_issues)
        mongo.db.issue_list.update({'_id': repo}, {'$set': {'updated_time': datetime.utcnow(),}}, upsert=True)
        r = mongo.db.issue_list.find_one({'_id': repo})

    return r['open_issues'] + r['closed_issues']


def detect_dup_issue(repo, num):
    cur_issue = mongo.db.issue.find_one({'repo': repo, 'num': num})

    issue_list = get_raw_issues(repo)
    issue_dict = dict([(issue['number'], issue) for issue in issue_list])
    
    global model
    model_save_id = repo + '_issue'
    if (model is None) or (model.save_id != model_save_id):
        title_list = [str(issue['title']) for issue in issue_list]
        body_list = [str(issue['body']) for issue in issue_list]
        model = nlp_model.Model([wordext.get_words_from_text(doc) for doc in (title_list + body_list)], model_save_id)

    det_ret = {}
    issueA = issue_dict[num]
    for issueB in issue_list:
        det_ret[issueB['number']] = (model.query_sim_tfidf(issueA['title'], issueB['title']) + model.query_sim_tfidf(issueA['body'], issueB['body'])) / 2

    sorted_ret = [(x,y) for x, y in sorted(det_ret.items(), key=lambda x: x[1], reverse=True)]
    num2, sim = sorted_ret[0]

    data = {'num2': num2, 'proba': sim, 'num2_data': issue_dict[num2]}
    mongo.db.issue_det.update({'_id': cur_issue['_id']}, {'$set': data}, upsert=True)


@app.route('/refresh_one_issue', methods=['GET', 'POST'])
def refresh_one_issue():
    repo = request.args.get('repo').strip()
    num = request.args.get('num').strip()
    if not (repo and num):
        raise Exception('Params Error!')

    detect_dup_issue(repo, num)
    return True


@app.route('/refresh_all', methods=['GET', 'POST'])
def refresh_all():
    repo = request.args.get('repo').strip()
    if not repo:
        raise Exception('Params Error!')

    open_issue_list = get_raw_issues(repo, 'only_open')
    for issue in open_issue_list:
        detect_dup_issue(repo, issue['number'])
    return True


@app.route('/<path:repo>', methods=['GET', 'POST'])
def dashboard(repo):
    open_issue_list = get_raw_issues(repo, 'only_open')
    return render_template('issues.html', repo=repo, issue_list=open_issue_list)


@app.route('/index')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=debug_flag)
