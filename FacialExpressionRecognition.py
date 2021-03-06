from keras.preprocessing import image
import warnings
warnings.filterwarnings("ignore")
import time
import os
from os import path
import numpy as np
import pandas as pd
from tqdm import tqdm
import json
import cv2
from keras import backend as K
import keras
import tensorflow as tf
import pickle

from basemodels import VGGFace, OpenFace, Facenet, FbDeepFace
from extendedmodels import Age, Gender, Race, Emotion
from commons import functions, realtime, distance as dst

def verify(img1_path, img2_path=''
	, model_name ='VGG-Face', distance_metric = 'cosine', model = None, enforce_detection = True):

	tic = time.time()

	if type(img1_path) == list:
		bulkProcess = True
		img_list = img1_path.copy()
	else:
		bulkProcess = False
		img_list = [[img1_path, img2_path]]

	#------------------------------

	if model == None:
		if model_name == 'VGG-Face':
			print("Using VGG-Face model backend and", distance_metric,"distance.")
			model = VGGFace.loadModel()

		elif model_name == 'OpenFace':
			print("Using OpenFace model backend", distance_metric,"distance.")
			model = OpenFace.loadModel()

		elif model_name == 'Facenet':
			print("Using Facenet model backend", distance_metric,"distance.")
			model = Facenet.loadModel()

		elif model_name == 'DeepFace':
			print("Using FB DeepFace model backend", distance_metric,"distance.")
			model = FbDeepFace.loadModel()

		else:
			raise ValueError("Invalid model_name passed - ", model_name)
	else: #model != None
		print("Already built model is passed")

	#------------------------------
	#face recognition models have different size of inputs
	input_shape = model.layers[0].input_shape[1:3]

	#------------------------------

	#tuned thresholds for model and metric pair
	threshold = functions.findThreshold(model_name, distance_metric)

	#------------------------------
	pbar = tqdm(range(0,len(img_list)), desc='Verification')
	
	resp_objects = []
	
	#for instance in img_list:
	for index in pbar:
	
		instance = img_list[index]
		
		if type(instance) == list and len(instance) >= 2:
			img1_path = instance[0]
			img2_path = instance[1]

			#----------------------
			#crop and align faces

			img1 = functions.detectFace(img1_path, input_shape, enforce_detection = enforce_detection)
			img2 = functions.detectFace(img2_path, input_shape, enforce_detection = enforce_detection)

			#----------------------
			#find embeddings

			img1_representation = model.predict(img1)[0,:]
			img2_representation = model.predict(img2)[0,:]

			#----------------------
			#find distances between embeddings

			if distance_metric == 'cosine':
				distance = dst.findCosineDistance(img1_representation, img2_representation)
			elif distance_metric == 'euclidean':
				distance = dst.findEuclideanDistance(img1_representation, img2_representation)
			elif distance_metric == 'euclidean_l2':
				distance = dst.findEuclideanDistance(dst.l2_normalize(img1_representation), dst.l2_normalize(img2_representation))
			else:
				raise ValueError("Invalid distance_metric passed - ", distance_metric)

			#----------------------
			#decision

			if distance <= threshold:
				identified =  "true"
			else:
				identified =  "false"

			#----------------------
			#response object

			resp_obj = "{"
			resp_obj += "\"verified\": "+identified
			resp_obj += ", \"distance\": "+str(distance)
			resp_obj += ", \"max_threshold_to_verify\": "+str(threshold)
			resp_obj += ", \"model\": \""+model_name+"\""
			resp_obj += ", \"similarity_metric\": \""+distance_metric+"\""
			resp_obj += "}"

			resp_obj = json.loads(resp_obj) #string to json

			if bulkProcess == True:
				resp_objects.append(resp_obj)
			else:
				#K.clear_session()
				return resp_obj
			#----------------------

		else:
			raise ValueError("Invalid arguments passed to verify function: ", instance)

	#-------------------------

	toc = time.time()

	#print("identification lasts ",toc-tic," seconds")

	if bulkProcess == True:
		resp_obj = "{"

		for i in range(0, len(resp_objects)):
			resp_item = json.dumps(resp_objects[i])

			if i > 0:
				resp_obj += ", "

			resp_obj += "\"pair_"+str(i+1)+"\": "+resp_item
		resp_obj += "}"
		resp_obj = json.loads(resp_obj)
		return resp_obj
		#return resp_objects


def analyze(img_path, actions = [], models = {}, enforce_detection = True):

	if type(img_path) == list:
		img_paths = img_path.copy()
		bulkProcess = True
	else:
		img_paths = [img_path]
		bulkProcess = False

	#---------------------------------

	#if a specific target is not passed, then find them all
	if len(actions) == 0:
		actions= ['emotion', 'age', 'gender', 'race']

	print("Actions to do: ", actions)

	#---------------------------------

	if 'emotion' in actions:
		if 'emotion' in models:
			print("already built emotion model is passed")
			emotion_model = models['emotion']
		else:
			emotion_model = Emotion.loadModel()

	if 'age' in actions:
		if 'age' in models:
			print("already built age model is passed")
			age_model = models['age']
		else:
			age_model = Age.loadModel()

	if 'gender' in actions:
		if 'gender' in models:
			print("already built gender model is passed")
			gender_model = models['gender']
		else:
			gender_model = Gender.loadModel()

	if 'race' in actions:
		if 'race' in models:
			print("already built race model is passed")
			race_model = models['race']
		else:
			race_model = Race.loadModel()
	#---------------------------------

	resp_objects = []
	
	global_pbar = tqdm(range(0,len(img_paths)), desc='Analyzing')
	
	#for img_path in img_paths:
	for j in global_pbar:
		img_path = img_paths[j]

		resp_obj = "{"

		#TO-DO: do this in parallel

		pbar = tqdm(range(0,len(actions)), desc='Finding actions')

		action_idx = 0
		img_224 = None # Set to prevent re-detection
		#for action in actions:
		for index in pbar:
			action = actions[index]
			pbar.set_description("Action: %s" % (action))

			if action_idx > 0:
				resp_obj += ", "

			if action == 'emotion':
				emotion_labels = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']
				
				img = functions.detectFace(img_path, target_size = (48, 48), grayscale = True, enforce_detection = enforce_detection)

				emotion_predictions = emotion_model.predict(img)[0,:]

				sum_of_predictions = emotion_predictions.sum()

				emotion_obj = "\"emotion\": {"
				for i in range(0, len(emotion_labels)):
					emotion_label = emotion_labels[i]
					emotion_prediction = 100 * emotion_predictions[i] / sum_of_predictions

					if i > 0: emotion_obj += ", "

					emotion_obj += "\"%s\": %s" % (emotion_label, emotion_prediction)

				emotion_obj += "}"

				emotion_obj += ", \"dominant_emotion\": \"%s\"" % (emotion_labels[np.argmax(emotion_predictions)])

				resp_obj += emotion_obj

			elif action == 'age':
				if img_224 is None:
					img_224 = functions.detectFace(img_path, target_size = (224, 224), grayscale = False, enforce_detection = enforce_detection) #just emotion model expects grayscale images
				#print("age prediction")
				age_predictions = age_model.predict(img_224)[0,:]
				apparent_age = Age.findApparentAge(age_predictions)

				resp_obj += "\"age\": %s" % (apparent_age)

			elif action == 'gender':
				if img_224 is None:
					img_224 = functions.detectFace(img_path, target_size = (224, 224), grayscale = False, enforce_detection = enforce_detection) #just emotion model expects grayscale images
				#print("gender prediction")

				gender_prediction = gender_model.predict(img_224)[0,:]

				if np.argmax(gender_prediction) == 0:
					gender = "Woman"
				elif np.argmax(gender_prediction) == 1:
					gender = "Man"

				resp_obj += "\"gender\": \"%s\"" % (gender)

			elif action == 'race':
				if img_224 is None:
					img_224 = functions.detectFace(img_path, target_size = (224, 224), grayscale = False, enforce_detection = enforce_detection) #just emotion model expects grayscale images
				race_predictions = race_model.predict(img_224)[0,:]
				race_labels = ['asian', 'indian', 'black', 'white', 'middle eastern', 'latino hispanic']

				sum_of_predictions = race_predictions.sum()

				race_obj = "\"race\": {"
				for i in range(0, len(race_labels)):
					race_label = race_labels[i]
					race_prediction = 100 * race_predictions[i] / sum_of_predictions

					if i > 0: race_obj += ", "

					race_obj += "\"%s\": %s" % (race_label, race_prediction)

				race_obj += "}"
				race_obj += ", \"dominant_race\": \"%s\"" % (race_labels[np.argmax(race_predictions)])

				resp_obj += race_obj

			action_idx = action_idx + 1

		resp_obj += "}"

		resp_obj = json.loads(resp_obj)

		if bulkProcess == True:
			resp_objects.append(resp_obj)
		else:
			return resp_obj

	if bulkProcess == True:
		resp_obj = "{"

		for i in range(0, len(resp_objects)):
			resp_item = json.dumps(resp_objects[i])

			if i > 0:
				resp_obj += ", "

			resp_obj += "\"instance_"+str(i+1)+"\": "+resp_item
		resp_obj += "}"
		resp_obj = json.loads(resp_obj)
		return resp_obj
		#return resp_objects


def detectFace(img_path):
	img = functions.detectFace(img_path)[0] #detectFace returns (1, 224, 224, 3)
	return img[:, :, ::-1] #bgr to rgb

def find(img_path, db_path
	, model_name ='VGG-Face', distance_metric = 'cosine', model = None, enforce_detection = True):
		
	tic = time.time()
	
	if type(img_path) == list:
		bulkProcess = True
		img_paths = img_path.copy()
	else:
		bulkProcess = False
		img_paths = [img_path]
	
	if os.path.isdir(db_path) == True:
		
		#---------------------------------------
		
		if model == None:
			if model_name == 'VGG-Face':
				print("Using VGG-Face model backend and", distance_metric,"distance.")
				model = VGGFace.loadModel()
			elif model_name == 'OpenFace':
				print("Using OpenFace model backend", distance_metric,"distance.")
				model = OpenFace.loadModel()
			elif model_name == 'Facenet':
				print("Using Facenet model backend", distance_metric,"distance.")
				model = Facenet.loadModel()
			elif model_name == 'DeepFace':
				print("Using FB DeepFace model backend", distance_metric,"distance.")
				model = FbDeepFace.loadModel()
			else:
				raise ValueError("Invalid model_name passed - ", model_name)	
		else: #model != None
			print("Already built model is passed")
		
		input_shape = model.layers[0].input_shape[1:3]
		threshold = functions.findThreshold(model_name, distance_metric)
		
		#---------------------------------------
		
		file_name = "representations_%s.pkl" % (model_name)
		file_name = file_name.replace("-", "_").lower()
		
		if path.exists(db_path+"/"+file_name):
			
			print("WARNING: Representations for images in ",db_path," folder were previously stored in ", file_name, ". If you added new instances after this file creation, then please delete this file and call find function again. It will create it again.")
			
			f = open(db_path+'/'+file_name, 'rb')
			representations = pickle.load(f)
			
			print("There are ", len(representations)," representations found in ",file_name)
			
		else:
			employees = []
			
			for r, d, f in os.walk(db_path): # r=root, d=directories, f = files
				for file in f:
					if ('.jpg' in file):
						exact_path = r + "/" + file
						employees.append(exact_path)
			
			if len(employees) == 0:
				raise ValueError("There is no image in ", db_path," folder!")
			
			#------------------------
			#find representations for db images
			
			representations = []
			
			pbar = tqdm(range(0,len(employees)), desc='Finding representations')
			
			#for employee in employees:
			for index in pbar:
				employee = employees[index]
				img = functions.detectFace(employee, input_shape, enforce_detection = enforce_detection)
				representation = model.predict(img)[0,:]
				
				instance = []
				instance.append(employee)
				instance.append(representation)
				
				representations.append(instance)
			
			f = open(db_path+'/'+file_name, "wb")
			pickle.dump(representations, f)
			f.close()
			
			print("Representations stored in ",db_path,"/",file_name," file. Please delete this file when you add new identities in your database.")
		
		#----------------------------
		#we got representations for database
		df = pd.DataFrame(representations, columns = ["identity", "representation"])
		df_base = df.copy()
		
		resp_obj = []
		
		global_pbar = tqdm(range(0,len(img_paths)), desc='Analyzing')
		for j in global_pbar:
			img_path = img_paths[j]
		
			#find representation for passed image
			img = functions.detectFace(img_path, input_shape, enforce_detection = enforce_detection)
			target_representation = model.predict(img)[0,:]
		
			distances = []
			for index, instance in df.iterrows():
				source_representation = instance["representation"]
				
				if distance_metric == 'cosine':
					distance = dst.findCosineDistance(source_representation, target_representation)
				elif distance_metric == 'euclidean':
					distance = dst.findEuclideanDistance(source_representation, target_representation)
				elif distance_metric == 'euclidean_l2':
					distance = dst.findEuclideanDistance(dst.l2_normalize(source_representation), dst.l2_normalize(target_representation))
				else:
					raise ValueError("Invalid distance_metric passed - ", distance_metric)
				
				distances.append(distance)
		
			df["distance"] = distances
			df = df.drop(columns = ["representation"])
			df = df[df.distance <= threshold]
		
			df = df.sort_values(by = ["distance"], ascending=True).reset_index(drop=True)
			resp_obj.append(df)
			df = df_base.copy() #restore df for the next iteration
			
		toc = time.time()
		
		print("find function lasts ",toc-tic," seconds")
		
		if len(resp_obj) == 1:
			return resp_obj[0]
		
		return resp_obj
		
	else:
		raise ValueError("Passed db_path does not exist!")
		
	return None
	
def stream(db_path = '', model_name ='VGG-Face', distance_metric = 'cosine', enable_face_analysis = True):
	realtime.analysis(db_path, model_name, distance_metric, enable_face_analysis)

def allocateMemory():
	print("Analyzing your system...")
	functions.allocateMemory()

functions.initializeFolder()

#---------------------------

