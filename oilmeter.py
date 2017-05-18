import math
import datetime
import cv2
import io
import numpy as np
import httplib
import time
import gspread
import oauth2client
import httplib2
import os
import base64
import email.mime
import mimetypes
from oauth2client.service_account import ServiceAccountCredentials
from apiclient import discovery, errors
from oauth2client import client
from oauth2client import tools
from email.mime.text import MIMEText
from oauth2client.file import Storage
from email.MIMEMultipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

scope = 'https://spreadsheets.google.com/feeds https://www.googleapis.com/auth/gmail.compose'
creds = ServiceAccountCredentials.from_json_keyfile_name('client_secret.json', scope)
client_sheets = gspread.authorize(creds)
CLIENT_SECRET_FILE = 'gmail_secret.json'
APPLICATION_NAME = 'oil_email'


camera_port = 1
ramp_frames = 30
camera = cv2.VideoCapture(camera_port)
 
#Takes Picture
def get_image():
 retval, im = camera.read()
 return im
 
for i in xrange(ramp_frames):
 temp = get_image()
print("Taking image...")
image = get_image()
file = "test_image.jpg"
cv2.imwrite(file, image)
del(camera)

#Rotate
#image = cv2.transpose(image)
#image = cv2.flip(image, 0)

# Grayscale
img = image
imggray = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
imggray = cv2.blur(imggray,(5,5))
ret,imgbinary = cv2.threshold(imggray, 50, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
ret,imgbinary = cv2.threshold(imggray, ret + 30, 255, cv2.THRESH_BINARY)

#find largest blob, the white background of the meter
# switch for pc/pi, depending if running on pi library or PC return value may require 2 or 3 vars
imgcont, contours,hierarchy = cv2.findContours(imgbinary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
# contours,hierarchy = cv2.findContours(imgbinary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
maxarea = 0
index = 0
meterContour = 0
for c in contours:
    area = cv2.contourArea(c)
    if (area > maxarea):
        maxarea = area
        meterContour = index
    index = index + 1

# find the largest child blob of the white background, should be the needle
maxarea = 0
index = hierarchy[0, meterContour, 2]
needleContour = 0
while (index >= 0):
    c = contours[index]
    area = cv2.contourArea(c)
    if (area > maxarea):
        maxarea = area
        needleContour = index
    index = hierarchy[0,index,0]

# find the largest child blob of the needle contour, should be only one, the pivot point
maxarea = 0
index = hierarchy[0, needleContour, 2]
pivotContour = 0
while (index >= 0):
    c = contours[index]
    area = cv2.contourArea(c)
    if (area > maxarea):
        maxarea = area
        pivotContour = index
    index = hierarchy[0,index,0]

# compute line from contour and point of needle, from this we will get the measurement angle
# the line however lacks direction and may be off +/- 180 degrees, use the pivot centroid to fix
[line_vx,line_vy,line_x,line_y] = cv2.fitLine(contours[needleContour],2,0,0.01,0.01)
needlePt = (line_x,line_y)

# moments of the pivot contour, and the centroid of the pivot contour
pivotMoments = cv2.moments(contours[pivotContour])
pivotPt = (int(pivotMoments['m10'] / pivotMoments['m00']), int(pivotMoments['m01'] / pivotMoments['m00']))

# find the vector from the pivot centroid to the needle line center
dx = needlePt[0] - pivotPt[0]
dy = needlePt[1] - pivotPt[1]

# if dot product of needle-pivot vector and line is negative, flip the line direction
# so the line angle will be oriented correctly
if (line_vx * dx + line_vy * dy < 0):
    line_vx = -line_vx;
    line_vy = -line_vy;

# with the corrected line vector, compute the angle and convert to degrees
line_angle = math.atan2(line_vy, line_vx) * 180 / math.pi

# normalize the angle of the meter
# the needle will go from approx 135 on the low end to 35 degrees on the high end
normangle = line_angle
# adjust the ranage so it doesn't wrap around, 135 to 395
if (normangle < 90): normangle = normangle + 360
# set the low end to 0,  0 to 260
normangle = normangle - 135
# normalize to percentage
pct = normangle / 260.0
print pct

# for display / archive purposes crop the image to the meter view using bounding box
minRect = cv2.minAreaRect(contours[meterContour])
box = cv2.boxPoints(minRect)
box = np.int0(box)

# draw the graphics of the box and needle
cv2.drawContours(img,[box],0,(0,0,255),4)
cv2.drawContours(img,contours,meterContour,(0,255,0),4)
cv2.drawContours(img,contours,needleContour,(255,0,0),4)
nsize = 120
cv2.line(img,(line_x-line_vx*nsize,line_y-line_vy*nsize),(line_x+line_vx*nsize,line_y+line_vy*nsize),(0,0,255),4)

#find min/max xy for cropping
minx = box[0][0]
miny = box[0][1]
maxx = minx
maxy = miny
for i in (1, 3):
    if (box[i][0] < minx): minx = box[i][0]
    if (box[i][1] < miny): miny = box[i][1]
    if (box[i][0] > maxx): maxx = box[i][0]
    if (box[i][1] > maxy): maxy = box[i][1]

# display the percentage above the bounding box
cv2.putText(img,"{:4.1f}%".format(pct * 100),(minx+150,miny-0),cv2.FONT_HERSHEY_SIMPLEX,3.0,(0,255,255),4)

# scale the extents for some background in the cropping
cropscale = 1.5
len2x = cropscale * (maxx - minx) / 2;
len2y = cropscale * (maxy - miny) / 2 ;
len2x = len2y / 3 * 4
avgx = (minx + maxx) / 2
avgy = (miny + maxy) / 2

# find the top-left, bottom-right crop points
cminx = int(avgx - len2x);
cminy = int(avgy - len2y);
cmaxx = int(avgx + len2x);
cmaxy = int(avgy + len2y);

# crop the image and output
imgcrop = img[cminy:cmaxy, cminx:cmaxx]
cv2.imwrite("oil.jpg", imgcrop)

# display for debugging
#imgscaled = cv2.resize(img, (0, 0), 0, 0.2, 0.2)
#imgcropscaled = cv2.resize(imgcrop, (0, 0), 0, 0.5, 0.5)
#cv2.imshow("output", imgscaled)
#cv2.imshow("outputcrop", imgcropscaled)

# create a timestamp for logging
def timestr(fmt="%Y-%m-%d %H:%M:%S "):
    return datetime.datetime.now().strftime(fmt)

# log the result
with open('angle.log','a') as outf:
    outf.write(timestr())
    outf.write('{:5.1f} deg {:4.1%}\n'.format(line_angle, pct))

percentageLeft = '{:4.1f}'.format(pct * 100)

#Google Drive Data Log (Sheet 2)
row = [timestr(), pct]
sheet2 = client_sheets.open('OilTankData').get_worksheet(1)
sheet2.insert_row(row)
result = sheet2.row_values(1)
sheetsPerc = result[1]
sheetsPerc = float(sheetsPerc)

#Gmail API
try:
    import argparse
    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None

def SendMessage(service, user_id, message): # Send an email message.
    try:
      message = (service.users().messages().send(userId=user_id, body=message)
               .execute())
      print ('Message Id: %s' % message['id'])
      return message
    except errors.HttpError as error:
      print ('An error occurred: %s' % error)

def get_credentials(): # Gets valid user credentials from disk.
    credential_dir = 'C:\Users\\antth\Documents\GitHub\OilLevelReader'
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'gmail_python.json')

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, scope)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials

def create_message(sender, to, subject, message_text): # Create a message for an email.
    message = MIMEText(message_text)
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    return {'raw': base64.urlsafe_b64encode(message.as_string())}

def mail(sender, recepient, subject, text_body ):
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('gmail', 'v1', http=http)
    testMessage = create_message_with_attachment(sender, recepient, subject, text_body, 'oil.jpg' )
    SendMessage(service, sender, testMessage )

def create_message_with_attachment(sender, to, subject, message_text, file):
  message = MIMEMultipart()
  message['to'] = to
  message['from'] = sender
  message['subject'] = subject

  msg = MIMEText(message_text)
  message.attach(msg)

  content_type, encoding = mimetypes.guess_type(file)

  if content_type is None or encoding is not None:
    content_type = 'application/octet-stream'
  main_type, sub_type = content_type.split('/', 1)
  if main_type == 'text':
    fp = open(file, 'rb')
    msg = MIMEText(fp.read(), _subtype=sub_type)
    fp.close()
  elif main_type == 'image':
    fp = open(file, 'rb')
    msg = MIMEImage(fp.read(), _subtype=sub_type)
    fp.close()
  elif main_type == 'audio':
    fp = open(file, 'rb')
    msg = MIMEAudio(fp.read(), _subtype=sub_type)
    fp.close()
  else:
    fp = open(file, 'rb')
    msg = MIMEBase(main_type, sub_type)
    msg.set_payload(fp.read())
    fp.close()
  filename = os.path.basename(file)
  msg.add_header('Content-Disposition', 'attachment', filename=filename)
  message.attach(msg)
  return {'raw': base64.urlsafe_b64encode(message.as_string())}

#Google Drive Data Log (Sheet 3)
sheet3 = client_sheets.open('OilTankData').get_worksheet(2)
result = sheet3.col_values(2)
full = float(result[0])
threequart = float(result[1])
half = float(result[2])
onequart = float(result[3])
ten = float(result[4])
five = float(result[5])
one = float(result[6])

#Email
recepient_email = ''
sender_email = ''
subject_box = 'Oil Tank Level'
body_box = 'The oil tank has ' + percentageLeft + "% of its oil remaining."

#Check if tank has been filled since last script run
num = sheet2.col_values(2)
first = float(num[0])
second = float(num[1])

if(second + .1) < first: 
    for x in range (1, 7):
        sheet3.update_cell(x,2, 0)  
               
#send email
if sheetsPerc < .01 and one == 0:
    #mail(sender_email, recepient_email, subject_box, body_box)
    sheet3.update_cell(7,2, 1)
    one = 1
elif sheetsPerc > .01 and sheetsPerc <= .05 and five == 0:
    #mail(sender_email, recepient_email, subject_box, body_box)
    sheet3.update_cell(6,2, 1)
    five = 1
elif sheetsPerc > .05 and sheetsPerc <= .10 and ten == 0:
    #mail(sender_email, recepient_email, subject_box, body_box)
    sheet3.update_cell(5,2, 1)
    ten = 1
elif sheetsPerc > .10 and sheetsPerc <= .25 and onequart == 0:
    #mail(sender_email, recepient_email, subject_box, body_box)
    sheet3.update_cell(4,2, 1)
    onequart = 1
elif sheetsPerc > .25 and sheetsPerc <= .50 and half == 0:
    #mail(sender_email, recepient_email, subject_box, body_box)
    sheet3.update_cell(3,2, 1)
    half = 1
elif sheetsPerc > .50 and sheetsPerc <= .75 and threequart == 0:
    #mail(sender_email, recepient_email, subject_box, body_box)
    sheet3.update_cell(2,2, 1)
    threequart = 1
elif sheetsPerc > .75 and sheetsPerc <= 1 and full == 0:
    #mail(sender_email, recepient_email, subject_box, body_box)
    sheet3.update_cell(1,2, 1)
    full = 1