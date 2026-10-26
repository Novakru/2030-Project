import socket
import threading
# from .device import ChemputerDevice
from queue import Queue
import time
import logging

# Network constants:
TCP_PORT = 5000
BUFFERSIZE = 1024


class _SimTCPEthernetDevice:
    def __init__(self):
        self.logger = logging.getLogger("main_logger.sim_logger")

class _TCPEthernetDevice:
    def __init__(self, address, name="", auto_init=True):
        # variables needed for connection
        self.name = name
        self.address = str(address)
        self.network_cfg = {}
        self.logger = logging.getLogger("main_logger.other_logger")
        self.device_ready_flag = threading.Event()
        self.queue = Queue()
        # TCP 
        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._connect_to_server()

        self.tcp_response_thread = threading.Thread(
            target=self._receive_response, name="{0} TCP thread".format(name),)
        self.tcp_response_thread.daemon = True
        self.tcp_response_thread.start()

        # --COMMANDS STRINGS--
        self.IP_READ = "{IPR}"
        self.IP_WRITE = "{IPW}"
        self.NAME_READ = "{NAM}"
        self.NAME_WRITE = "{NAW}"
        self.ETH_CFG_W = "{ETW}"
        self.ETH_CFG_R = "{ETH}"
        self.DONE = "DONE"        
        
        # make sure device is operational if `auto_init` is set
        if auto_init:
            self.is_connected()
            #pass # For future improvement if in case



    def __del__(self):
        """
        Destructor that closes the server connection and joins all threads.
        """
        self.tcp.close()
        try:
            self.tcp_response_thread.join()
        except AttributeError:
            pass

    def _connect_to_server(self):
        """
        Attempts to connect to the TCP server.

        Raises:
            Exception (OSException): The connection has failed.
        """
        try:
            self.tcp.connect((self.address, TCP_PORT))
            self.logger.debug("Connected to device {0}.".format(self.name))
            # self.tcp.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # turn on the TCP keepalive
            # self.tcp.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 1000, 1000))  # configure to send a keepalive packet every second
        except Exception:
            self.logger.exception("Unable to connect to host device: IP {0} did not respond.".format(self.address))

    def disconnect(self):
        """
        Disconnect from device. Needs to be called to reinstantiate device
        object within the same Python process.
        """
        self.logger.debug("Disconnecting from device...")
        self.queue.put("disconnect")
        # Must be called before joining thread as tcp_response_thread gets
        # stuck in self.tcp.recv(...) so doesn't always get disconnect message
        # in queue.
        self.tcp.close()
        self.tcp_response_thread.join()
        self.logger.debug("Disconnected from device.")

    def _should_disconnect(self):
        """Return True if thread should finish, otherwise False.

        Returns:
            bool: True if thread should finish, otherwise False.
        """
        if not self.queue.empty():
            queue_item = self.queue.get()
            if queue_item == "disconnect":
                self.queue.task_done()
                return True
        return False

    def _receive_response(self):
        """
        Receive a response from TCP socket and parse it
        """
        while True:
            if self._should_disconnect():
                return
            try:
                response = self.tcp.recv(BUFFERSIZE).decode()

            except(TimeoutError, ConnectionResetError, ConnectionAbortedError):
                self.logger.exception("Device {0} has disconnected.".format(self.name))
                return  # TODO raise disconnection error

            if not response:
                continue
            
            elif self.DONE in response:
                self.logger.debug(response)
                self.device_ready_flag.set()
            
            elif self.address in response:
                self.logger.debug(response)
                self.logger.info("{0} Connected".format(self.name))
                self.device_ready_flag.set()

            else:
                self.logger.info(response)
                continue

    def _build_command(self, *cmds):
        """
        Builds the command string from a varying list of arguments, adding a null-terminated character

        Args:
            cmds (Variadic): List of commands to create the string.
        """
        cmd_string = ""
        for cmd in cmds:
            cmd_string += (str(cmd) + " ")

        return cmd_string[:-1] + "\n\0"
          
    def _send_command(self, *cmds):
        """
        Constructs the command string and sends it to the TCP server.

        Args:
            cmds (Variadic): List of commands used to create the string.
        """
        self.device_ready_flag.clear()
        cmd = self._build_command(*cmds)
        # print(cmd.encode()) # Debug printout
        try:
            self.tcp.send(cmd.encode())
        except ConnectionResetError:
            self.logger.exception("Device {0} has disconnected.".format(self.name))  # TODO raise connection error

    def wait_until_ready(self):
        """
        Waits until the device is ready by listening for a DONE command from the server.
        This then sets the flag that the operation has completed.
        """
        # set = self.device_ready_flag.is_set()  # TODO statement seems to have no effect
        self.device_ready_flag.wait()
        time.sleep(0.1)
    
    def is_connected(self):
        """
        Ask for the IP of the device to confirm the connection
        """
        self._send_command(self.IP_READ)
        self.device_ready_flag.wait()



