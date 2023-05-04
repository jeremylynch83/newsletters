from flask import Flask, Response, json, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_login import current_user, login_user, login_required, logout_user
from models import db, userModel, publicModel, login
import requests
import os
import secrets
from werkzeug.utils import secure_filename
from bs4 import BeautifulSoup

class CustomFlask(Flask):
    jinja_options = Flask.jinja_options.copy()
    jinja_options.update(dict(
        block_start_string='<%',
        block_end_string='%>',
        variable_start_string='%%',
        variable_end_string='%%',
        comment_start_string='<#',
        comment_end_string='#>',
    ))

app = CustomFlask(__name__, static_folder='static')
secret = secrets.token_urlsafe(32)
app.secret_key = secret
first_request = True


########################
# Setup login         ##
########################


# Link our user SQLite database with SQLALchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user_templates.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Create the database file before the first user request itself
@app.before_request
def create_table():
    global first_request
    if first_request:
        first_request = False
        db.create_all()

# Generate a unique ID for templates/modules in database
def unique_id():
    new_id = 1
    while publicModel.query.filter_by(id = new_id).first() != None:
        new_id = new_id + 1
    return new_id
        

# Link the login instance to our app 
login.init_app(app)
login.login_view = 'login'

@app.route('/login', methods=['POST', 'GET'])
def login():
    print("login")

    if current_user.is_authenticated:
            data = {
                "username": current_user.get_username(),
                "templates_modules": current_user.get_templates_modules(),
                "prefs": current_user.get_prefs()
            }
            return jsonify(data)
     
    if request.method == 'POST':
        req = request.get_json()
        email = req["user_email"]
        user = userModel.query.filter_by(email = email).first()
        if user is not None and user.check_password(req['user_password']):
            login_user(user)
            return redirect('/app-page')

        if user is None or not user.check_password(req['user_password']):
            return "failure", 400
    

@app.route('/check-login', methods=['GET'])
def check_login():
    if current_user.is_authenticated:
            data = {
                "templates_modules": current_user.get_templates_modules(),
                "username": current_user.get_username(),
                "prefs": current_user.get_prefs()
            }
            return jsonify(data)
    else:
        return "failure", 200

@app.route('/import-templates', methods=['POST', 'GET'])
def import_templates():
    if current_user.is_authenticated:
        with app.open_resource('static/xml/neuro.xml') as f:
            str = f.read().decode('utf-8')
            data = {
                "templates_modules": str,
            }
            return jsonify(data)
    else:
        return "failure", 200

# Register new user
@app.route('/register', methods=['POST', 'GET'])
def register():
    print("register")
    req = request.get_json()

    if current_user.is_authenticated:
        return redirect('/')
     
    if request.method == 'POST':
        email = req["user_email"]
        username = req["user_name"]
        password = req["user_password"]
        starter_data = ""
        with app.open_resource('static/xml/starter.xml') as f:
            starter_data = f.read().decode('utf-8')

        if userModel.query.filter_by(email=email).first():
            return ('Email already Present'), 400

        user = userModel(email=email, username=username)
        user.set_password(password)
        user.save_templates_modules(starter_data)
        db.session.add(user)
        db.session.commit()
        return "success"

# Logout
@app.route('/logout', methods=['POST'])
def logout():
    logout_user()
    return redirect('/')

# Saves user templates and modules
@app.route('/index/export', methods=['POST'])
def export_module():
    req = request.get_json()
    xml = req["xml"]
    current_user.save_templates_modules(xml)
    db.session.add(current_user)
    db.session.commit()
    return req

# Saves user preferences
@app.route('/save-prefs', methods=['POST'])
def save_prefs():
    req = request.get_json()
    #print(json.dumps(req))
    current_user.save_prefs(json.dumps(req))
    db.session.add(current_user)
    db.session.commit()
    return req

# Add a new template to the template store
@app.route('/publish-template', methods=['POST'])
def publish_template():
    req = request.get_json()
    template = req["template"]
    modules = req["modules"]
    public = publicModel(id = unique_id(), name=template["name"], modality = template["modality"], region = template["region"], specialty = template["specialty"], type_of = publicModel.TEMPLATE_TYPE, owner = current_user.get_username(), meta = "meta", xml =template["xml"])
    if publicModel.query.filter_by(name = template["name"]).first() == None:
        db.session.add(public)

    for n in modules:
        if publicModel.query.filter_by(name = n["name"]).first() == None:
            module = publicModel(id = unique_id(), name=n["name"], modality = "NA", region = "NA", specialty = "NA", type_of = publicModel.MODULE_TYPE, owner = current_user.get_username(), meta = "meta", xml =n["xml"])
            db.session.add(module)

    db.session.commit()    
    return "success"

# Add a group of templates to the template store
@app.route('/bulk-publish-template', methods=['POST'])
def bulk_publish_template():
    req = request.get_json()
    templates = req["templates"]
    modules = req["modules"]

    for template in templates:
        public = publicModel(id = unique_id(), name=template["name"], modality = template["modality"], region = template["region"], specialty = template["specialty"], type_of = publicModel.TEMPLATE_TYPE, owner = current_user.get_username(), meta = "meta", xml =template["xml"])
        if publicModel.query.filter_by(name = template["name"]).first() == None:
            db.session.add(public)

    for n in modules:
        if publicModel.query.filter_by(name = n["name"]).first() == None:
            module = publicModel(id = unique_id(), name=n["name"], modality = "NA", region = "NA", specialty = "NA", type_of = publicModel.MODULE_TYPE, owner = current_user.get_username(), meta = "meta", xml =n["xml"])
            db.session.add(module)

    db.session.commit()    
    return "success"


# Get list of all templates on store
@app.route('/store-list', methods=['GET'])
def store_list():
    data = db.session.query(publicModel).all()
    t = []
    for n in data:
        item = {
            "name": n.name,
            "id": n.id,
            "type": n.type_of,
            "region": n.region,
            "specialty": n.specialty, 
            "modality": n.modality
        }
        t.append(item)
    return jsonify(t)

# Get list of user templates on store
@app.route('/store-user-list', methods=['GET'])
def store_user_list():
    data = db.session.query(publicModel).all()
    t = []
    for n in data:
        if n.owner == current_user.get_username():
            item = {
                "name": n.name,
                "id": n.id,
                "type": n.type_of,
                "region": n.region,
                "specialty": n.specialty, 
                "modality": n.modality
            }
            t.append(item)

    return jsonify(t)

# Get data of store template from name
@app.route('/store-get-templates', methods=['POST', 'GET'])
def store_get_templates():
    req = request.get_json()
    xml = "<all>"
    # Add all the templates selected
    for n in req:
        t = publicModel.query.filter_by(id=n["id"]).first()
        soup = BeautifulSoup(t.xml, 'xml')
        xml_temp = "<template><name>" + t.name + '</name><region>' + t.region + '</region><specialty>' + t.specialty + '</specialty><modality>' + t.modality + '</modality>' + t.xml + '</template>'

        def get_modules(xml_soup, xml_temp2):
            module_list = xml_soup.find_all(['insert', 'query_insert'])
            for m in module_list:
                module = publicModel.query.filter_by(name=m.decode_contents()).first()
                if module != None:        
                    xml_temp2 = xml_temp2 +"<module><name>" + module.name + '</name><content>' + module.xml + '</content></module>'
                    xml_temp2 = get_modules(BeautifulSoup('<content>' + module.xml + '</content>', 'xml'), xml_temp2)
            return xml_temp2
        xml = xml + get_modules(soup, xml_temp)
    xml = xml + '</all>'
    return jsonify(xml)

# Deletes selected templates from the store
@app.route('/store-delete-templates', methods=['POST'])
def store_delete_templates():
    req = request.get_json()
    for n in req:
        t = publicModel.query.filter_by(id=n["id"]).first()
        db.session.delete(t)
    db.session.commit()
    return "success"


# Return list of all templates on radreport.com (cached on server)
@app.route('/radreport-list', methods=['GET'])
def radreport_list():
    list = ""
    with app.open_resource('static/js/radreportlist.json') as f:
        list = f.read().decode('utf-8')
    return list

@app.route('/radreport-get-template', methods=['POST', 'GET'])
def radreport_get_template():
    req = request.get_json();
    x = requests.get('https://api3.rsna.org/radreport/v1/templates/' + req["template_id"] + '/details?' + req["template_version"]).text
    x_json = json.loads(x)
    y = BeautifulSoup(x_json["DATA"]["templateData"], features="lxml").prettify()
    data = {
                "xml": y,
                "template_id": req["template_id"],
                "template_version": req["template_version"]
            }
    return jsonify(data)

@app.route('/', methods = ['POST', 'GET'])
def index():
    news_content = read_news_content()
    #return news_content
    return render_template('newsletter.html', title='Newsletter', news_content=news_content)

@app.route('/newsletter', methods = ['POST', 'GET'])
def newsletter():
    news_content = read_news_content()
    #return news_content
    return render_template('newsletter.html', title='Newsletter', news_content=news_content)

@app.route('/app-page', methods = ['POST', 'GET'])
def app_page():
    return render_template('app.html', title='radiologytemplates.org')

@app.route('/store', methods = ['POST', 'GET'])
def store():
    return render_template('store.html', title='radiologytemplates.org')

@app.route('/user', methods = ['POST', 'GET'])
def user():
    return render_template('user.html', title='radiologytemplates.org')

def read_news_content():
    data_folder = os.path.join(app.root_path, 'data')
    news_content = ""
    with open(os.path.join(data_folder, 'news.html'), 'r') as file:
        news_content = file.read()
    return news_content





if __name__ == '__main__':
    app.run()
