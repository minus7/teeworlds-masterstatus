#!/usr/bin/env python3
# vim: set ts=4 sw=4 noet:

import asyncio
import time
import struct
from operator import attrgetter
import sys
import argparse

class MasterInfo:
	name = ""
	server_count = None
	latency = None
	status = ""

	def __repr__(self):
		if not self.server_count or not self.latency:
			return "<MasterInfo {name} {status}>".format(name=self.name, status=self.status)
		return "<MasterInfo {name} {status} ({servers} servers, {lat_ms:.0f}ms)>".format(name=self.name, status=self.status, servers=self.server_count, lat_ms=(self.latency*1000))

class MasterCountProtocol(asyncio.DatagramProtocol):
	packet_count_request = 10*b'\xff' + b'cou2'
	packet_count_response = 10*b'\xff' + b'siz2'

	def __init__(self):
		self.waiter = asyncio.Future()

	def response(self):
		return self.waiter

	def connection_made(self, transport):
		transport.sendto(self.packet_count_request)
		self.time_start = time.monotonic()

	def datagram_received(self, data, addr):
		if len(data) <= len(self.packet_count_response) or not data.startswith(self.packet_count_response):
			return # that's not it, wait for more
		info = MasterInfo()
		info.latency = time.monotonic() - self.time_start
		response = data[len(self.packet_count_response):]
		info.server_count = struct.unpack('!H', response)[0]
		info.status = "ok"
		self.waiter.set_result(info)
	
	def error_received(self, exc):
		self.waiter.set_exception(exc)


masters = {
	"master1": ("master1.teeworlds.com", 8300),
	"master2": ("master2.teeworlds.com", 8300),
	"master3": ("master3.teeworlds.com", 8300),
	"master4": ("master4.teeworlds.com", 8300),
	"website": ("teeworlds.com", 8300),
}

@asyncio.coroutine
def query_master(name, addr, loop, timeout=1):
	try:
		transport, protocol = yield from loop.create_datagram_endpoint(MasterCountProtocol, remote_addr=addr)
		masterinfo = yield from asyncio.wait_for(protocol.response(), timeout=timeout)
	except asyncio.TimeoutError:
		masterinfo = MasterInfo()
		masterinfo.status = "timeout"
	except:
		masterinfo = MasterInfo()
		masterinfo.status = "error"
	masterinfo.name = name
	return masterinfo

def html_print(masterinfos, file=sys.stdout):
	print('<div id="masterstatus">', file=file)
	print("<table><thead><tr><th>Name</th><th>Status</th><th>Servers</th><th>Latency</th></tr></thead><tbody>", file=file)
	for masterinfo in masterinfos:
		if not masterinfo.server_count or not masterinfo.latency:
			print("<tr><td>{name}</td><td>{status}</td><td>-</td><td>-</td></tr>".format(name=masterinfo.name, status=masterinfo.status), file=file)
		else:
			print("<tr><td>{name}</td><td>{status}</td><td>{servers}</td><td>{lat_ms:.0f}ms</td></tr>".format(name=masterinfo.name, status=masterinfo.status, servers=masterinfo.server_count, lat_ms=(masterinfo.latency*1000)), file=file)
	print("</tbody></table>", file=file)
	print('</div>', file=file)

@asyncio.coroutine
def update(output_filename, loop):
	results = [asyncio.async(query_master(name, addr, loop=loop)) for name, addr in masters.items()]
	done, pending = yield from asyncio.wait(results, loop=loop)
	with open(output_filename, "w") as f:
		masterinfos = list(sorted(map(asyncio.Future.result, done), key=attrgetter("name")))
		html_print(masterinfos, file=f)

@asyncio.coroutine
def main(loop):
	p = argparse.ArgumentParser()
	p.add_argument("output", help="html output file name")
	args = p.parse_args()

	while True:
		yield from update(args.output, loop)
		yield from asyncio.sleep(10)

if __name__ == "__main__":
	loop = asyncio.get_event_loop()
	loop.run_until_complete(main(loop))
