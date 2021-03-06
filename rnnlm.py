from __future__ import print_function

import sys
import numpy as np
import math
import pickle
import txt

from keras.models import Sequential, Model, load_model
from keras.layers import Input, Dense, Activation, Dropout, concatenate
from keras.layers.embeddings import Embedding
from keras.layers.recurrent import LSTM
from keras.optimizers import SGD
from keras.utils import to_categorical
from datetime import datetime

def initModelNew(params, embSize = 512, hdnSize = 1024, catEmbSize = 8):
	# main input
	inputs = [Input(shape=(params.max, len(params.w2i)))]

	# inputs for each additional cat
	for i, cat2idx in enumerate(params.c2i):
		inputs.append(Input(shape=(params.max, len(cat2idx))))

	# feed-forward embeddings for each input separately
	embeddings = [Dense(embSize if i == 0 else catEmbSize, activation='linear')(inLayer) for i, inLayer in enumerate(inputs)]

	if len(embeddings) == 1:
		hidRec1 = Dropout(0.2)(LSTM(hdnSize, return_sequences=True)(embeddings[0]))
	else:
		embConc = concatenate(embeddings)
		hidRec1 = Dropout(0.2)(LSTM(hdnSize, return_sequences=True)(embConc))
	
	hidRec2 = Dropout(0.2)(LSTM(hdnSize, return_sequences=True)(hidRec1))

	output = Dense(len(params.w2i), activation='softmax')(hidRec2)

	model = Model(inputs=inputs, outputs=[output])
	model.compile(loss='sparse_categorical_crossentropy', optimizer='adam')

	return model

#def initModelOld(vocSize, maxLen, embSize = 512, hdnSize = 1024):
#	model = Sequential()
#
#	model.add(Embedding(input_dim = vocSize, output_dim = embSize, input_length = maxLen))
#
#	model.add(LSTM(hdnSize, input_shape=(maxLen, embSize), return_sequences=True))
#	model.add(Dropout(0.2))
#
#	model.add(LSTM(hdnSize, input_shape=(maxLen, hdnSize), return_sequences=True))
#	model.add(Dropout(0.2))
#
#	model.add(Dense(vocSize))
#	model.add(Activation('softmax'))
#
#	model.compile(loss='sparse_categorical_crossentropy', optimizer='adam')
#
#	return model

def renorm(pd, temp = 0.5):
	raw = [p**(1/temp) for p in pd]
	raw[txt.OOV] = 0
	s = sum(raw)
	return [p/s for p in raw]

def sample(mdl, params, catVecs, temp = 1.0):
	vocSize = len(params.w2i)
	
	baseInput = np.zeros([1, params.max, vocSize], dtype='int32')
	
	result = []
	wIdx = txt.SOS
	
	prob = 0.0
	
	for i in range(params.max):
		baseInput[0, i, wIdx] = 1
		
		pd = mdl.predict([baseInput] + catVecs)[0, i]
		
		#w = max(enumerate(pd), key=lambda x: x[1] if x[0] != OOV else 0)[0]
		wIdx = np.random.choice(vocSize, p = renorm(pd, temp))
		prob += math.log(pd[wIdx])
		
		if wIdx == txt.EOS:
			break
		
		result.append(wIdx)
	
	return result, prob / (len(result)+1)

def batchLog(data, params, mdl, counter, numSamples = 5):
	print(str(datetime.now()), "minibatches:", counter, "loss:", str(mdl.evaluate(data.getJointInput(), data.out)))
	for _ in range(numSamples):
		spec, vec = txt.rndCatVec(params)
		currentSample, currProb = sample(mdl, params, vec, temp = 0.4)
		sampleStr = "".join([params.i2w[i] for i in currentSample if i > 0])
		print(str(datetime.now()), "cat:", str(spec), "sample:", sampleStr, "prob:", currProb)

def learn(mdl, params, txtdata, batchSize = 64, reportFreq = 200):
	#mdl.fit(data.getJointInput(), data.out, epochs=1, batch_size=32)
	
	bStart = 0
	counter = 0
	while bStart < len(txtdata):
		bEnd = bStart + batchSize
		
		batchData = txt.getIOData(txtdata[bStart:bEnd], params)
		
		#batchIn = data.getJointInput(start=bStart, end=bEnd)
		#batchOut = data.out[bStart:bEnd]
		
		mdl.train_on_batch(batchData.getJointInput(), batchData.out)
		
		if counter % reportFreq == 0:
			batchLog(batchData, params, mdl, counter)
		
		bStart = bEnd
		counter += 1

def score(snt, models, catVecs, skipEOS = False):
	(mdl, dicts) = models
	
	data = txt.getIOData([snt], dicts)
	
	hyps = mdl.predict(data.getJointInput())
	
	result = 0
	length = 0
	
	for j, pVec in enumerate(hyps[0]):

		#inp = inputs[0, j] # correct is inputs[0, j, X]
		outp = outputs[0, j, 0] #data.out
		
		#if inp == 0 or (skipEOS and outp == EOS):
		#	break
		
		#print(j, outp, pVec)
		
		length += 1
		result += math.log(pVec[outp])
		
	return result / length


def score_sents_nocat(snts, models):
	(mdl, dicts) = models
	data = txt.getIOData_nocat(snts, dicts)

	hyps = mdl.predict(data.getJointInput())

	results = []
	inputs, outputs = data.txtIn, data.out
	for hyp in hyps:

		result = 0
		length = 0
		for j, pVec in enumerate(hyp):
			outp = outputs[0, j, 0]

			length += 1
			result += math.log(pVec[outp])
		results.append(result/length)

	return results


def score_sent_nocat(sent, models):
	(mdl, dicts) = models
	data = txt.getIOData_nocat([sent], dicts)

	hyps = mdl.predict(data.getJointInput())
	hyp = hyps[0]

	inputs, outputs = data.txtIn, data.out
	result = 0
	length = 0
	for j, pVec in enumerate(hyp):
		outp = outputs[0, j, 0]

		length += 1
		result += math.log(pVec[outp])
	return result/length

def loadModels(modelFile, paramFile):
	mdl = load_model(modelFile)
	
	with open(paramFile, 'rb') as fh:
		params = pickle.load(fh)
	
	return (mdl, params)

def saveParams(metaparams, filename):
	with open(filename, 'wb') as fh:
		pickle.dump(metaparams, fh, protocol=pickle.HIGHEST_PROTOCOL)
