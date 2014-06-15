import unirest
import rauth
import os
import sys

# TODO: integrate more sources than just yelp
# TODO: get bus/travel times, etc.
# TODO: perhaps transfer this in a web servie of some sort?

## Keys, Constants
# TransLoc Mashape API Key
transloc_url = "https://transloc-api-1-2.p.mashape.com/"
transloc_mashape_key = os.environ.get('TRANSLOC_MASHAPE_KEY')

# Yelp API 2.0
yelp_consumer_key = os.environ.get('YELP_CONSUMER_KEY')
yelp_consumer_secret = os.environ.get('YELP_CONSUMER_SECRET')
yelp_token = os.environ.get('YELP_TOKEN')
yelp_token_secret = os.environ.get('YELP_TOKEN_SECRET')

if not transloc_mashape_key:
	print 'Missing an important API key environment variable, please double check to make sure the following is present:'
	print '		TRANSLOC_MASHAPE_KEY'
	sys.exit(1)
elif not yelp_consumer_key:
	print 'Missing an important API key environment variable, please double check to make sure the following is present:'
	print '		YELP_CONSUMER_KEY'
	sys.exit(1)
elif not yelp_consumer_secret:
	print 'Missing an important API key environment variable, please double check to make sure the following is present:'
	print '		YELP_CONSUMER_SECRET'
	sys.exit(1)
elif not yelp_token:
	print 'Missing an important API key environment variable, please double check to make sure the following is present:'
	print '		YELP_TOKEN'
	sys.exit(1)
elif not yelp_token_secret:
	print 'Missing an important API key environment variable, please double check to make sure each of the following is present:'
	print '		YELP_TOKEN_SECRET'
	sys.exit(1)

## Utils
def mashape_header():
	headers = { "X-Mashape-Authorization": transloc_mashape_key }
	return headers

# http://www.yelp.com/developers/documentation/v2/search_api#searchMSL
# http://letstalkdata.com/2014/02/how-to-use-the-yelp-api-in-python/
def get_yelp_results(params): 
	session = rauth.OAuth1Session(consumer_key = yelp_consumer_key,
				      consumer_secret = yelp_consumer_secret,
				      access_token = yelp_token,
				      access_token_secret = yelp_token_secret)
		            
	request = session.get("http://api.yelp.com/v2/search",params=params)
			    
	data = request.json()
	session.close()
				     
	return data

# TODO: This is hard coded to Slater Rd, Durham for testing
def find_me():
	return 35.877908, -78.842137

def url_paramify(entities, key):
	entity_ids = ''
        for entity in entities:
                entity_ids += entity[key] + ','
        entity_ids = entity_ids[:-1]
	return entity_ids

## TransLoc
def find_nearby_agencies(latitude, longitude):
	radius = 800
        close = '%s,%s|%s'%(latitude, longitude, radius)
	agencies = unirest.get("https://transloc-api-1-2.p.mashape.com/agencies.json?geo_area=%s"%close, 
			   headers=mashape_header()).body['data']
	return agencies

def find_nearest_stops(latitude, longitude, agencies, radius=800):
	close = '%s,%s|%s'%(latitude, longitude, radius)
	stops_resp = unirest.get("https://transloc-api-1-2.p.mashape.com/stops.json?agencies=%s&geo_area=%s"%
					(url_paramify(agencies, 'agency_id'), close), 
				 headers=mashape_header())
	return stops_resp.body['data']

def find_nearest_routes(latitude, longitude, agencies, radius=800):
        close = '%s,%s|%s'%(latitude, longitude, radius)
        routes_resp = unirest.get("https://transloc-api-1-2.p.mashape.com/routes.json?agencies=%s&geo_area=%s"%
					(url_paramify(agencies, 'agency_id'), close),
                                 headers=mashape_header())
        return routes_resp.body['data']

## Yelp
def get_gf_search_parameters(lat,long):
	  params = {}
	  params["term"] = "restaurant"
	  params["category_filter"] = 'gluten_free'
	  params["ll"] = "{},{}".format(str(lat),str(long))
	  params["radius_filter"] = "800" # ~ half a mile
	  params["limit"] = "10"
		     
	  return params

def find_gluten_free(latitude, longitude):
	params = get_gf_search_parameters(latitude, longitude)
	return get_yelp_results(params)

def find_gf_free_near_stops(stops):
	#stop_coords = {stop['stop_id']:(stop['location']['lat'], stop['location']['lng']) for stop in stops}
	stop_coords = {}
	for stop in stops:
		location = stop['location']['lat'], stop['location']['lng']
		stop_coords[stop['stop_id']] = location

	restaurants = {}
	for stop_id,coords in stop_coords.iteritems():
		restaurants[stop_id] = find_gluten_free(*coords)['businesses']
	
	return restaurants

def find_route_to_restaurant(routes, nearby_stops, restaurants):
	nearby_stop_set = set([stop['stop_id'] for stop in nearby_stops])
	possible_routes_to_restaurants = {}
	for restaurant, info in restaurants.iteritems():
		stops_near_restaurant_set = set(info['nearby_stops'])

		for route_id, stops in routes.iteritems():
			route_stop_set = set(stops)
			if not route_stop_set.isdisjoint(nearby_stop_set) and not route_stop_set.isdisjoint(stops_near_restaurant_set):
				if restaurant in possible_routes_to_restaurants:
					possible_routes_to_restaurants[restaurant].append(route_id)
				else:
					possible_routes_to_restaurants[restaurant] = [route_id]
	return possible_routes_to_restaurants

# TODO: actually put the stop that's near them on the darn return value... :/
def find_guten_free_near_me(my_lat, my_long, search_radius=9000):
	agencies = find_nearby_agencies(my_lat, my_long)
	nearest_stops = find_nearest_stops(my_lat, my_long, agencies, radius=search_radius)
	nearest_routes = find_nearest_routes(my_lat, my_long, agencies, radius=search_radius)

	nearest_routes_by_stop = {}
	for agency in nearest_routes:
		routes = nearest_routes[agency]
		for route in routes:
			if route['is_active']:
				nearest_routes_by_stop[route['route_id']] = route['stops']

	gf_restaurants = {}
	gf_restaurant_candidates = find_gf_free_near_stops(nearest_stops)
	for stop_id, restaurants in gf_restaurant_candidates.iteritems():
		if restaurants:
			for restaurant in restaurants:
				loc = ''
				for seg in restaurant['location']['display_address']:
					loc += seg + ", "
				loc = loc[:-1]
				if (restaurant['name'],loc) not in gf_restaurants:
					restaurant['nearby_stops'] = [stop_id]
					gf_restaurants[(restaurant['name'],loc)] = restaurant
				else:
					gf_restaurants[(restaurant['name'],loc)]['nearby_stops'].append(stop_id)

	routes_to_restaraunt = find_route_to_restaurant(nearest_routes_by_stop, nearest_stops, gf_restaurants)
	return routes_to_restaraunt

#print(find_guten_free_near_me(*find_me()))
