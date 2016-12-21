#!/usr/bin/env python
# -*- coding: utf-8 -*-
import cgi			# CGI
import cgitb		# CGI - debug exception handler
import urlparse
from datetime import datetime
import os
import sys
import json
import PyJSONSerialization
import traceback

SCRIPT_VERSION      = "v1.3"
BRANCHES_STATUS     = "branches_status.json" # JSON status of branches
MAX_BRANCH_PER_PAGE = 11

CSS = '''
html { 
  height: 100%;
}

* {
  margin: 0;
  padding: 0;
  background-color: #000000;
  font-color: #FFFFFF;
  color: #FFFFFF;
}

#titre {
  font-size: 3.5em;
  font-family: "Arial", Arial, sans-serif;
  text-align: center;
}

#ctx_menu {
  visibility: hidden;
  position: absolute;
  display: inline;
  background: #554444;
}

table {
  margin: 5px 0 30px 0;
}

table tr th, table tr td {
  background: #554444;
  color: #FFF;
  border-radius: 8px;
  padding: 8px 4px;
  font-family: "Arial", Arial, sans-serif;
  text-align: center;
}

table tr th {
  font-size: 1.6em;
}

table tr td {
  background: #444444;
  font-size: 2em;
}

table .branch {
  font-size: 3em;
  text-align: left;
}

table .pipeline { 
  background: #444444;
  text-align: center;
}

table .null { 
  background: #000000;
}

table .pending { 
  background: #000000;
  text-align: center;
  padding: 6px 14px;
  border-radius: 6px;
}

table .created { 
  background: #000000;
  text-align: center;
  padding: 6px 14px;
  border-radius: 6px;
}

table .running { 
  background: #444444;
  text-align: center;
  padding: 6px 14px;
  border-radius: 6px;
}

table .success { 
  background: #00BB00;
  text-align: center;
  padding: 6px 14px;
}

table .OK { 
  background: #00BB00;
  text-align: center;
  padding: 6px 14px;
}

table .failed {
  background: #DD0000;
  text-align: center;
  padding: 6px 14px;
}

a {
  text-decoration: none;
}'''

# activates a special exception handler that will display detailed reports in the Web browser if any errors occur
cgitb.enable()
sys.stderr = sys.stdout

def escape(txt):
	return cgi.escape(txt, True)

# Variant of a branch  - Allow to monitor different jobs 
# 1 variant = 1 column shown on the display
class VariantStatus:
	def __init__(self):
		self.build_id  = None
		self.status    = None # 'pending' 'created' 'skipped' 'running' 'success' 'failed' 'canceled' 'OK'
		self.previous  = None # 'success' 'failed' 'OK'
		self.url       = None

	@classmethod
	def create(cls, status, previous, url, build_id):
		retour = cls()
		retour.build_id   = build_id
		retour.status     = status
		retour.previous   = previous
		retour.url        = url
		return retour

# Status of a branch
class BranchStatus:
	def __init__(self):
		self.pipeline_id = 0
		self.url         = None
		self.variants    = dict()
		self.date_maj    = None

	def set_id(self, pipeline_id, url):
		self.pipeline_id = pipeline_id
		self.url         = url

	def set_result (self, variant, status, url, build_id):
		old_build_id = 0
		previous = None
		if self.variants.has_key(variant):
			old_build_id = self.variants[variant].build_id
			old_status   = self.variants[variant].status   # 'pending' 'created' 'skipped' 'running' 'success' 'failed' 'canceled' 'OK'
			old_previous = self.variants[variant].previous # 'success' 'failed' 'OK'
			# Update "previous" build status during a new build ("pending", "created", "running" or "canceled") if it was relevant ("success", "failed" or "OK")
			if (status == "pending" or status == "created" or status == "running" or status == "canceled") and (old_status == "success" or old_status == "failed" or old_status == "OK"):
				previous = self.variants[variant].status
			else: # Else, by default keep "previous" build status if any
				previous = old_previous
		# Only keep information on the most recent build for the variant
		if build_id >= old_build_id:
			self.variants[variant] = VariantStatus.create(status, previous, url, build_id)
			self.date_maj = datetime.now().isoformat()

	def force_result (self, variant, status):
		if self.variants.has_key(variant):
			url      = self.variants[variant].url
			build_id = self.variants[variant].build_id
		else:
			url      = None
			build_id = 0
		self.set_result(variant, status, url, build_id)


#########################################################################################################################
#
#          Main


save_to_file = False

# Load previous CI results from file
try:
	with open(BRANCHES_STATUS, "r") as f:
		branch_list = PyJSONSerialization.load(f.read(), globals())
except:
	branch_list = dict()

# Read parameters passed by the command line (CGI)
try:
	get_params = urlparse.parse_qs(os.environ['QUERY_STRING'])
	force_branch  = get_params['branch'][0]
	force_variant = get_params['variant'][0]
	force_status  = get_params['force_status'][0]
	if force_branch and force_variant and force_status:
		branch_list[force_branch].force_result(force_variant, force_status)
		save_to_file = True
except:
	pass

# Read json data (if available) in the body of the request
try:
  #json_status = json.load(sys.stdin)
	raw_data = sys.stdin.read()

	json_status = json.loads(raw_data)

	if json_status["object_kind"] == "pipeline":
		pipeline_id = json_status["object_attributes"]["id"]
		branch      = json_status["object_attributes"]["ref"]
		status      = json_status["object_attributes"]["status"] # 'pending' 'running' 'success' 'failed' 'canceled'
		builds      = json_status["builds"]
		web_url     = json_status["project"]["web_url"]

		# Update CI results only if there is a new result provided by the Gitlab CI Pipeline Webhook
		if branch not in branch_list:
			update = True
			branch_list[branch] = BranchStatus()
		elif pipeline_id == branch_list[branch].pipeline_id:
			update = True
		elif pipeline_id > branch_list[branch].pipeline_id:
			update = True
		else:
			update = False

		if update:
			url = web_url + "/pipelines/" + str(pipeline_id)  
			branch_list[branch].set_id(pipeline_id, url)
			save_to_file = True

			for build in builds:
				variant   = build["name"]
				status    = build["status"]
				build_id  = build["id"]
				url       = web_url + "/builds/" + str(build_id)  
				branch_list[branch].set_result(variant, status, url, build_id)

	elif json_status["object_kind"] == "build":
		branch   = json_status["ref"]
		variant  = json_status["build_name"]
		build_id = json_status["build_id"]
		status   = json_status["build_status"]
		web_url  = json_status["repository"]["homepage"]
		url      = web_url + "/builds/" + str(build_id)  

		if branch in branch_list:
			if variant in branch_list[branch].variants:
				if build_id == branch_list[branch].variants[variant].build_id:
					if status != branch_list[branch].variants[variant].status:
						branch_list[branch].set_result(variant, status, url, build_id)
						save_to_file = True
				elif build_id > branch_list[branch].variants[variant].build_id:
					branch_list[branch].set_result(variant, status, url, build_id)
					save_to_file = True

except ValueError as exception:
	# no data, this is not a Gitlab request
	pass
except Exception as exception:
	pass


if save_to_file:
	# Save results to file
	with open(BRANCHES_STATUS, "w") as f:
		f.write (PyJSONSerialization.dump(branch_list))


# ###############################################################
# Display CI results
#
# Build a table showing :
# - Branch name
# - status of all the build variants of this branch

print '''Content-type: text/html; charset=utf-8'

<html>
<head>
  <title>Branch status</title>
  <meta http-equiv="refresh" content="15">
  <style>''' + CSS + '''</style>
</head>
<script language="javascript" type="text/javascript">
function ShowMenu(self, e) {
console.log(self.id)
  var posx = e.clientX + window.pageXOffset + 'px'; // Left Position of Mouse Pointer
  var posy = e.clientY + window.pageYOffset + 'px'; // Top Position of Mouse Pointer
  var menu = self.querySelectorAll("#ctx_menu")[0];
  menu.style.visibility = 'visible';
  menu.style.position = 'absolute';
  menu.style.display = 'inline';
  menu.style.left = posx;
  menu.style.top = posy;
  self.onmouseleave = function(){menu.style.visibility = 'hidden';};
  
  return false;
}
</script>
'''

# Iterate through branch list to extract the list of variants, and split job names in two parts
variant_list = [] # all job names, then splited in two parts : "quick:linux" => [quick, linux]
stage_list   = [] # stages (build/test/deploy) from first part of the job name
os_list      = [] # OSs (linux/windows) from second part of the job name
for branch_name, branch_status in branch_list.iteritems():
	for variant_name, variants in branch_status.variants.iteritems():
		if variant_name not in variant_list:
			variant_list.append(variant_name)
			variant_title = variant_name.split(":", 1)
			stage = variant_title[0]
			if stage not in stage_list:
				stage_list.append(stage)
			os = variant_title[1]
			if os not in os_list:
				os_list.append(os)
os_list.sort()

# Header of the table
print '''<div id="titre">Branch Status</div>'''
print '''<table>'''
print '''<tr>'''
print '''  <th/>'''
for os in os_list:
	print '''  <th colspan="'''+str(len(stage_list))+'''" class="titre">''' + os.capitalize() + '''</td>''' # extract "quick" and "linux" from "quick:linux"
print '''</tr>'''

# Iterate through branches sorted by date of the last update
cpt = 0
for (branch_name, branch_status) in sorted(branch_list.items(), key=lambda(k,v): v.date_maj, reverse=True):
#	if branch_status.url:
#		print '''<tr>\n  <td rawspan="'''+str(len(os_list))+'''" class="branch"><a class="pipeline" href="'''+branch_status.url+'''">''' + branch_name + '''</a></td>'''
#	else:
	print '''<tr>\n  <td class="branch">''' + branch_name + '''</a></td>'''

	# Add all results in their respective columns
	for os in os_list:
		for stage in stage_list:
			variant = stage+":"+os
			try:
				status   = branch_status.variants[variant].status
				previous = branch_status.variants[variant].previous
				if not previous:
					previous = status
				url      = branch_status.variants[variant].url
				if url:
					href = ''' href="''' + url + '''"'''
				else:
					href = ""
				print '''  <td class="''' + previous + '''" onContextMenu="return ShowMenu(this, event);">
    <div id="ctx_menu">
      <a href="?branch=''' + escape(branch_name) + '''&variant=''' + escape(variant) + '''&force_status=OK"/>Force OK</a>
    </div>
    <a class="''' + status + '"' + href + '''> </a>
  </td>'''
			except KeyError:
				# The variant doesn't exists for this branch
				print '  <td class="null" />'

	print '</tr>'
	cpt += 1
	if cpt >= MAX_BRANCH_PER_PAGE:
		# Stop when whe reach the maximum number of branch to display
		break
	
print '''</table>
'''+SCRIPT_VERSION+'''
</html>'''
