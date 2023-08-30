import influxdb_client, os, time
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from pprint import PrettyPrinter
from collectDisplay import getCurrentData
import asyncio

'''
This module reads the moving average value of all the host from influx db
compares with the threshold and if above threshold, adds the host to victim_set 
for each host in victim_set: gets flagged container from json and rtt values wrt all other host
for all host in host_set: gets available resources
for each flagged containers, get required resources, compares with available resources of host_set
if matched, available resource of host_set is reduced and migration is triggered.

data: victim_set, dest_set, dest_rtt, dest_resource, cntr_resource

'''

pp = PrettyPrinter(indent=2)
# To create a empty set, the built in method is used:
victim_set = set()
dest_set = set()
dest_rtt = {}
dest_resource = {} 
cntr_resource = {}

dbdata= {}
thresold = 20

def connectToDB():
  token = 'UnZq8-3qAHW4bk5BNjZgPJLBeeNkOXWatintbu4RAZe_96fdRbPHofP_sE6JWNEPrTnGyFUg26ofUifZQx19DA=='
  #mac_token = "tKQMaN6mMBXH-gDotw6qvpEOvcZNIMILQWTH1LTKFDddf3e4owp48cG88bFae1L_H3H5Tp8GV0jrDdzBjQiRhQ=="
  org = "LSBU"
  url = "http://localhost:8086"
  client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
  return client

def readFromDB(client):
  #querying data from db
  query_api = client.query_api()  
  query = """
  from(bucket: "telemetrydata")
	|> range(start: -1d)
  |> filter(fn: (r) => r["_measurement"] == "test7")
  |> filter(fn: (r) => r["_field"] == "cpu_utilization" or r["_field"] == "storage_free" or r["_field"] == "vm_free")
  """

  tables = query_api.query(query, org="LSBU")
  for table in tables:
      for record in table.records:
        dest_set.add(record['host'])
        if record['host'] in dbdata:
          dbdata[record['host']].update({record['_field'] : record['_value']})        
        else:
           dbdata[record['host']] = {record['_field'] : record['_value']} 
           
def getVictimHost():  
  #convert to scalar value
  hostlist = dest_set.copy()
  for host in hostlist:
    cumulativeValue = dbdata[host]['cpu_utilization'] + dbdata[host]['storage_free'] + dbdata[host]['storage_free']  #create better function

    #compare with thresold
    if cumulativeValue > thresold:
      #if above thresold - > #delete from dest_set, add into victim list 
      victim_set.add(host)  
      #remove victim from host set
      dest_set.discard(host)

#update the dest_resource with the available resource details
def updateDestResource(host, cpu_utilization):
    dest_resource[host] = {'cpu':cpu_utilization} 

#update the cntr_resource with the available resource details
def updateVictimCntrResource(host, container, cpu, nw, vm):
    cntr_resource[container] = {'cpu':cpu, 'nw':nw, 'vm':vm, 'host':host } 

#checks if a container can be flagged as victim and updates it's resource requirement
def checkCntrResource(cntr, host):
     for id in cntr:
            cpu = id["cpu_stats"]["cpu_usage"]["total_usage"]
            nw = id['networks']['eth0']['rx_errors']
            vm = id["memory_stats"]["usage"]
            container = id['id']
            if cpu+nw+vm > 2000:
                updateVictimCntrResource(host, container, cpu, nw, vm)

#takes the combined API return value to update both victim and destination resources
def updateResourceDetails(deviceData3):
    for k in deviceData3:
        if k['host'] in dest_set:
            updateDestResource(k['host'], k['cpu_utilization'])
            
        elif k['host'] in victim_set:
         if 'containers' in k:
          checkCntrResource(k['containers'], k['host'])

#update the rtt data for victim nodes to available destination nodes
def updateRttData(rttData, victim):
    for dest in rttData:
        if victim in dest_rtt:
            dest_rtt[victim].update({dest['host'] : dest['avg_latency']})
        else:
            dest_rtt[victim] = {dest['host'] : dest['avg_latency']}

def getRTTforVictim():
    # for all hosts in victim_set 
    for victim in victim_set:
        #call api and get values
        rttData = [{'host': '8.8.8.8', 'avg_latency': 6.32, 'min_latency': 5.98, 'max_latency': 6.7, 'packet_loss': 0.0}, 
                   {'host': '8.8.8.5', 'avg_latency': 6.20, 'min_latency': 5.98, 'max_latency': 6.7, 'packet_loss': 0.0}, 
                   {'host': '8.8.8.5', 'avg_latency': 6.12, 'min_latency': 5.98, 'max_latency': 6.7, 'packet_loss': 0.0}, 
                   {'host': '10.35.84.127', 'avg_latency': 6.20, 'min_latency': 5.98, 'max_latency': 6.7, 'packet_loss': 0.0}, 
                   {'host': '192.168.122.210', 'avg_latency': 6.12, 'min_latency': 5.98, 'max_latency': 6.7, 'packet_loss': 0.0}
                   ]
        updateRttData(rttData, victim)

def selectBestRTTValue(list, srcIP):
    print(srcIP)
    print(dest_rtt)
    if srcIP in dest_rtt:
        rtt_values = dest_rtt[srcIP]
        # Creating a new dictionary with only the desired keys
        filtered_rtt = {key: value for key, value in rtt_values.items() if key in list}
        lowest_rtt = min(filtered_rtt.values())
        dest_IP = [key for key, value in filtered_rtt.items() if value == lowest_rtt][0]
    return dest_IP

def createSourceImage(srcIP, cntrId):
    pass
def copyToDestination(destIP):
    pass
def restoreInDestination(destIP):
    pass

def migrateVictimCntr():
    cntrId = ''
    srcIP = ''
    destIP = ''
    for key in cntr_resource:
        cntrId = key
        srcIP = cntr_resource[key]['host']
        demand = cntr_resource[key]
        IPlist = []
        for key in dest_resource:
            avail = dest_resource[key]
            if(demand['cpu'] > avail['cpu']):
                IPlist.append(key)
        destIP = selectBestRTTValue(IPlist, srcIP)
        createSourceImage(srcIP, cntrId)
        copyToDestination(destIP)
        restoreInDestination(destIP)

def startmonitoring():
  client = connectToDB()
  while 1:
    print("on work") # delete this
    readFromDB(client) 

    print(dbdata) 
    print(dest_set) 
    getVictimHost()

    print(victim_set)
    print(dest_set)   
    #if victimlist is not empty - search victim container and destination host - > trigger migration
    if victim_set:
      #call combined API to get real data instead of test data
      deviceData = asyncio.run(getCurrentData()) #change read host to  call combine data
      print(deviceData)
      #just for testing
      dest_set.add('192.168.122.210') 
      #updates details
      updateResourceDetails(deviceData)
      getRTTforVictim()

      #print updated resource after test
      print(dest_resource)
      print(cntr_resource)
      print(dest_rtt)

      migrateVictimCntr()
             
if __name__ == '__main__':
  startmonitoring()




