

import jfileutil as j

j.basepath_json = "./"

d = j.json_load("opera-net-export-log")

def makeUrlList(prefix, outfile):
	dis = [u for u in [
	  j.get('params').get('url') for j in d['events'] if j.get('params') is not None and j.get('params').get('url') is not None
	  ] if u[:len(prefix)] == prefix
	]
	dis = list(set(dis))
	j.json_save(dis, outfile)
	with open("./" + outfile + ".txt", "w") as outlist:
		outlist.writelines(map(lambda x: x + '\n', dis))
	
makeUrlList("https://cdn.discordapp.com/emojis","emojis")
makeUrlList("https://cdn.discordapp.com/avatars/","avatars")