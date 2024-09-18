from flask import Flask, render_template, request, jsonify, redirect, url_for
import openai
import requests
from urllib.parse import urlencode

app = Flask(__name__)

# Set your OpenAI API key
openai.api_key = "sk-6CkGy6lXZwHWr7sRoZRvFXcF1pnOgDa66wETKDxOy-T3BlbkFJWp2mv9ACKeA4vbVj4Wu43uDLRvOJ1Ze_qAJEouHyUA"
UNWRANGLE_API_KEY = "093b53f0ea19309bd5292b36205fe137567f50cd"

conversation_history = []

# Home page for entering ZIP code
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        zipcode = request.form['zipcode']
        return redirect(url_for('chat', zipcode=zipcode))
    return render_template('index.html')

# Chat page with nearby stores
@app.route('/chat/<zipcode>', methods=['GET'])
def chat(zipcode):
    stores = get_stores_near_zipcode(zipcode)
    return render_template('chat.html', stores=stores, zipcode=zipcode)

# Function to get stores from Unwrangle API
def get_stores_near_zipcode(zipcode):
    url = f"https://data.unwrangle.com/api/getter/?platform=lowes_store&zipcode={zipcode}&api_key={UNWRANGLE_API_KEY}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            return data.get('results', [])
    return []

@app.route('/store_chat/<store_number>', methods=['GET'])
def store_chat(store_number):
    store_name = request.args.get('store_name', 'Unknown Store')
    store_location = request.args.get('store_location', 'Unknown Location')
    
    # Print statements for debugging
    print(f"Store Name: {store_name}")
    print(f"Store Location: {store_location}")
    print(f"Store Number: {store_number}")
    
    # Pass the data to the template
    return render_template('store_chat.html', store_name=store_name, store_location=store_location, store_number=store_number)

# Function to get product search results from Unwrangle API using store number and search query
def search_products(query, store_number):
    params = {
        "platform": "lowes_search",
        "search": query.replace(" ", "+"),  # Handle spaces for search queries
        "store_no": store_number,
        "api_key": UNWRANGLE_API_KEY
    }
    encoded_params = urlencode(params)
    url = f"https://data.unwrangle.com/api/getter/?{encoded_params}"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            return data['results']
    return None


# Function to fetch product reviews from Unwrangle API using product URL
def get_product_reviews(product_url, page=1):
    params = {
        "platform": "lowes_reviews",
        "url": product_url,
        "page": page,
        "api_key": UNWRANGLE_API_KEY
    }
    encoded_params = urlencode(params)
    url = f"https://data.unwrangle.com/api/getter/?{encoded_params}"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            return data['reviews']
    return None

# OpenAI chatbot response with store number, product data, and reviews
@app.route('/send_message', methods=['POST'])
def send_message():
    user_input = request.form['message']
    store_number = request.form.get('store_number')  # Include store number in the chat

    # Add the user's message and store information to the conversation history
    conversation_history.append({"role": "user", "content": user_input})

    # Get the store details from the selected store
    store_name = request.form.get('store_name', 'None')
    store_location = request.form.get('store_location', 'None')

    # Search for products using the extracted query
    try:
        search_query = extract_search_query(user_input)  # Extract search query from user input
        if search_query:
            products = search_products(search_query, store_number)
            if products:
                # Initialize a general product section
                product_sections = {}

                # Categorize products based on the product name or attributes
                for product in products[:5]:  # Limit to top 5 results
                    product_name = product.get('name', 'Unknown product')
                    price = product.get('price', 'Unknown price')
                    url = product.get('url', 'No URL available')
                    stock_status = product.get('in_stock', False)
                    availability = "Yes, it's in stock!" if stock_status else "Sorry, it's currently out of stock."

                    # Categorize based on keywords in the product name or query
                    category = categorize_product(product_name)

                    if category not in product_sections:
                        product_sections[category] = []

                    # Append product details to the corresponding category in bullet format
                    product_sections[category].append(f"""
                        <li><strong>{product_name}</strong> <br>
                        Price: {price} <br>
                        Availability: {availability} <br>
                        <a href="{url}" target="_blank">More info</a></li>
                    """)

                # Build the final message for each section dynamically
                response_message = f"You selected {store_name} at {store_location}.<br><br>"
                response_message += f"Here are the relevant items we found at store number {store_number}:<br>"

                # Display products in bullet points under categories
                for section, items in product_sections.items():
                    if items:
                        response_message += f"<strong>{section}:</strong><br><ul>" + "".join(items) + "</ul><br>"

            else:
                response_message = f"I'm sorry, I couldn't retrieve any products matching your query for store {store_name}."

            # Append response to conversation history and return the response
            conversation_history.append({"role": "assistant", "content": response_message})
            return jsonify({'reply': response_message})

    except Exception as e:
        print(f"Error: {e}")  # Log the error for troubleshooting
        return jsonify({'error': str(e)})

    # In case no product info is found, respond with default OpenAI behavior
    try:
        # GPT model will know the context of the store number and the query
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Use 'gpt-4' if you have access
            messages=conversation_history,
            max_tokens=150,
            temperature=0.7
        )

        assistant_reply = response['choices'][0]['message']['content'].strip()
        conversation_history.append({"role": "assistant", "content": assistant_reply})

        return jsonify({'reply': assistant_reply})

    except Exception as e:
        return jsonify({'error': str(e)})


def categorize_product(product_name):
    """
    A function to dynamically categorize the product based on keywords in the product name.
    For example, if a product name contains 'cabinet', it will categorize it under 'Cabinets'.
    """
    if "cabinet" in product_name.lower():
        return "Cabinets"
    elif "countertop" in product_name.lower():
        return "Countertops"
    elif "sink" in product_name.lower():
        return "Sinks"
    elif "faucet" in product_name.lower():
        return "Faucets"
    elif "appliance" in product_name.lower() or "fridge" in product_name.lower() or "microwave" in product_name.lower():
        return "Appliances"
    elif "hammer" in product_name.lower() or "drill" in product_name.lower() or "tool" in product_name.lower():
        return "Tools"
    elif "paint" in product_name.lower() or "roller" in product_name.lower():
        return "Painting Supplies"
    else:
        return "Other Products"




def extract_search_query(user_input):
    # Basic keyword matching to detect product queries
    product_keywords = [
    "hammer", "cabinet", "lawn mower", "shovel", "drill", "furniture", "paint", "appliances",
    "screwdriver", "screws", "nails", "saw", "cordless drill", "pressure washer", "air conditioner",
    "heater", "fan", "dishwasher", "refrigerator", "stove", "oven", "microwave", "washer", "dryer",
    "flooring", "tiles", "carpet", "ceiling fan", "light bulbs", "chandelier", "blinds", "curtains",
    "door", "window", "shower", "bathtub", "faucet", "sink", "toilet", "mirror", "vanity", "countertop",
    "backsplash", "kitchen cabinets", "bathroom cabinets", "patio furniture", "grill", "charcoal",
    "fire pit", "garden hose", "garden tools", "wheelbarrow", "soil", "fertilizer", "mulch", "grass seed",
    "hedge trimmer", "leaf blower", "chainsaw", "pruning shears", "ladders", "workbench", "toolbox",
    "storage shelves", "garage door", "security camera", "smoke detector", "carbon monoxide detector",
    "locks", "deadbolt", "doorbell", "smart home", "thermostat", "smart light", "smart plug", "solar lights",
    "outdoor lights", "floodlight", "extension cords", "power strip", "surge protector", "batteries", 
    "generators", "inverter", "solar panels", "electric wiring", "breaker box", "outlets", "switches",
    "plumbing pipes", "PVC pipe", "copper pipe", "water heater", "water softener", "sump pump",
    "well pump", "submersible pump", "gas pipe", "paint brushes", "paint rollers", "paint sprayer", 
    "primer", "interior paint", "exterior paint", "paint thinner", "deck stain", "wood finish", 
    "varnish", "sealant", "caulk", "spackle", "drywall", "wall anchors", "stud finder", "measuring tape",
    "level", "square", "clamps", "wood screws", "metal screws", "hex bolts", "carriage bolts", "anchor bolts",
    "plywood", "hardwood", "2x4", "4x4", "concrete", "cement", "rebar", "masonry", "mortar", "bricks", 
    "pavers", "gravel", "sand", "asphalt", "driveway sealer", "roof shingles", "gutters", "downspouts", 
    "siding", "insulation", "weatherstripping", "caulking gun", "utility knife", "tape measure", 
    "socket wrench", "ratchet", "pliers", "adjustable wrench", "pipe wrench", "channel locks", 
    "multimeter", "wire stripper", "drill bits", "hole saw", "miter saw", "circular saw", "table saw",
    "reciprocating saw", "jigsaw", "orbital sander", "belt sander", "angle grinder", "router", "dremel", 
    "planer", "safety glasses", "hearing protection", "work gloves", "hard hat", "steel-toed boots", 
    "scaffolding", "tarp", "shop vacuum", "air compressor", "nail gun", "staple gun", "tack strips", 
    "concrete mix", "mortar mix", "epoxy", "tile adhesive", "grout", "caulking", "waterproofing", 
    "deck boards", "railing", "staircase", "balusters", "handrails", "concrete blocks", "retaining wall blocks",
    "fencing", "gate", "post", "lattice", "privacy screen", "landscape fabric", "garden edging", 
    "pond liner", "fountain pump", "sprinkler system", "irrigation", "drip irrigation", "composter", 
    "mulcher", "tiller", "snow blower", "salt spreader", "ice melt", "snow shovel", "roof rake", 
    "window air conditioner", "ceiling fan", "space heater", "humidifier", "dehumidifier", "air purifier"
]
    for keyword in product_keywords:
        if keyword in user_input.lower():
            return keyword
    return None

if __name__ == '__main__':
    app.run(debug=True)
