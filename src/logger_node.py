#! /usr/bin/env python

import rospy
import socket
import ssl
import time
import threading
import rosnode
from datetime import datetime
from sensor_msgs.msg import JointState
from edo_core_msgs.msg import JointReset


class TLSClientCommunication:
    ca_certs = "/home/ros/hrc_ws/src/logger/certificates/ca.crt"
    clt_cert = "/home/ros/hrc_ws/src/logger/certificates/client1.crt"
    clt_key = "/home/ros/hrc_ws/src/logger/certificates/client1.key"

    def __init__(self, ip_address, port):
        self.ip_address = ip_address
        self.port = port
        self.ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS)
        self.ssl_context.verify_mode = ssl.CERT_REQUIRED
        self.ssl_context.load_verify_locations(self.ca_certs)
        self.ssl_context.load_cert_chain(certfile=self.clt_cert, keyfile=self.clt_key)
        self.client_socket = socket.socket()
        self.secure_socket = None
        self.worker = None
        self.message_buffer = []
        self.roslogcounter = 0

    def connect(self):
        try:
            print("123")
            self.secure_socket = self.ssl_context.wrap_socket(self.client_socket)
            print("456")
            self.secure_socket.connect((self.ip_address, self.port))
            print("after connect")
        except Exception as e:
            print(e)

        self.__certificate_validator()
        self.__socket_reader()

    def close(self):
        if self.worker.isAlive():
            self.worker.stop()
        if self.secure_socket is not None:
            self.secure_socket.shutdown(socket.SHUT_RDWR)
            self.secure_socket.close()

    def socket_writer(self, msg):
        try:
            self.secure_socket.send(msg.encode())
        except Exception as e:
            print(e)
            rospy.signal_shutdown("Error writing in socket, shutting down node.")

    def __socket_reader(self):
        self.worker = ReadWorker(self.secure_socket)
        self.worker.daemon = True  # setting this as a daemon so the the thread is dependant to its claling process
        self.worker.start()

    def __certificate_validator(self):
        srv_cert = self.secure_socket.getpeercert()
        self.__validate_server_crt(srv_cert)
        self.__validate_crt_time(srv_cert)

    def __validate_server_crt(self, crt):
        subject = dict(item[0] for item in crt['subject'])
        commonName = subject['commonName']

        if not crt:
            raise Exception("Unable to retrieve server certificate")

        if commonName != 'edo_server':
            raise Exception("Incorrect common name in server certificate")

    def __validate_crt_time(self, crt):
        notAfterTimestamp = ssl.cert_time_to_seconds(crt['notAfter'])
        notBeforeTimestamp = ssl.cert_time_to_seconds(crt['notBefore'])
        currentTimeStamp = time.time()

        if currentTimeStamp > notAfterTimestamp:
            raise Exception("Expired server certificate")

        if currentTimeStamp < notBeforeTimestamp:
            raise Exception("Server certificate not yet active")

    def callback(self, data):
        self.message_buffer.append(str(data))


        # TODO here we are sending 1 out of 200 messages. There is some sort of bottleneck in the server.
        if len(self.message_buffer) > 200:
            #self.socket_writer(str(self.message_buffer[199]))
            now = datetime.now()
            self.socket_writer('Nodes running ' + str(now) + str(rosnode.get_node_names()))
            self.socket_writer('Machines connected ' + str(now) + str(rosnode.get_machines_by_nodes()))
            self.message_buffer = []


class ReadWorker(threading.Thread):
    def __init__(self, con_socket):
        threading.Thread.__init__(self)
        self.socket = con_socket
        self.running = True

    def run(self):
        print("read worker has started")
        publisher = rospy.Publisher('bridge_jnt_reset', JointReset, queue_size=2)
        try:
            while self.running:
                msg = self.socket.recv(1024)
                if msg == b'':
                    raise Exception("Client disconnected socket.")
                print("Message recieved " + msg.decode())
                if msg.decode() == "brake":
                    # TODO find a way to brake the robot with ROS.
                    print("breaking the robot -> not implemented")
                    pass
                if msg.decode() == "unbrake":
                    print("unbreaking the robot")
                    ros_msg = JointReset(63, 2000, 3.5)
                    publisher.publish(ros_msg)

        except Exception as e:
            print(e)
            raise e

    def stop(self):
        print("Worker socket close request")
        self.running = False
        print("Worker socked closed.")


def main():
    rospy.init_node('log_sender', anonymous=True)

    print("before connecting")
    tls_con = TLSClientCommunication("20.76.51.149", 15002)
    print("tls_con object initialized")
    tls_con.connect()

    rospy.Subscriber("joint_states", JointState, tls_con.callback)

    try:
        rospy.spin()
    finally:
        tls_con.close()
        rospy.signal_shutdown("shutting down the node")
        print("Shutting down")


if __name__ == '__main__':
    rospy.loginfo("Starting log sender node")
    main()
