from machine import Pin, reset
import time
import qwiic_bme280
import network
import socket
import secrets
import _thread
import asyncio
import gc

time.sleep(2) # allow usb connection on startup

temperature_threshold = 32  # Celsius

ssid = secrets.WIFI_SSID  # your SSID name stored in secrets.py
password = secrets.WIFI_PASSWORD  # your WiFi password stored in secrets.py

version = "1.2"
print("Cabinet Fan Controller - Version:", version)

status_led = Pin("LED", Pin.OUT)
fan_pin = Pin(20, Pin.OUT)

terminateThread = False

def connect_to_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    # Connect to network
    wlan.connect(ssid, password)
    connection_timeout = 10
    while connection_timeout > 0:
        if wlan.status() >= 3:
            break
        connection_timeout -= 1
        print('Waiting for Wi-Fi connection...')
        blink_led(status_led,1, 0.1)
        time.sleep(1)
    # Check if connection is successful
    if wlan.status() != 3:
        print('Failed to establish a network connection')
        return False
    else:
        print('Connection successful!')
        network_info = wlan.ifconfig()
        print('IP address:', network_info[0])
        return True
    
# HTML template for the webpage
def webpage():
    global temperature_value
    html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Cabinet Fan Controller</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <meta http-equiv="refresh" content="30">
        </head>
        <body>
            <h1>Cabinet Fan Controller</h1>
            <h2>Status</h2>
            <p>Current Temperature: {get_temperature(sensor)} &deg;C</p>
            <p>Fan state: {"ON" if fan_pin.value() == 1 else "OFF"}</p>
            <form action="/">
                <input type="submit" value="Refresh" />
            </form>
            <h2>--------------------------------</h2>
            <p>Temperature Threshold: {temperature_threshold} &deg;C</p>
            <form action="./temp_up">
                <input type="submit" value="Increase" />
            </form>
            <form action="./temp_down">
                <input type="submit" value="Decrease" />
            </form>
        </body>
        </html>
        """
    return str(html)

def fan(state):
    if state:
        fan_pin.on()
    else:
        fan_pin.off()

def blink_led(pin, times, interval):
    for _ in range(times):
        pin.on()
        time.sleep(interval) # sleep 
        pin.off()
        time.sleep(interval) # sleep 

def get_temperature(sensor):
    temperature = sensor.get_temperature_celsius()
    return temperature

def store_threshold(threshold):
    try:
        with open('current_threshold.txt', 'w') as f:
            f.write(str(temperature_threshold))
    except OSError:
        print("Failed to write threshold to file.")

def load_threshold():
    try:
        with open('current_threshold.txt', 'r') as f:
            threshold = int(f.read())
            return threshold
    except (OSError, ValueError):
        store_threshold(32) # initialize file if not present
        print("Failed to read threshold from file, initializing.")
        return 32

def manage_fan():
        gc.collect()
        print("Starting fan management thread")
        while terminateThread == False:
            temperature = get_temperature(sensor)
            print(f"Temperature: {temperature:.2f} C")

            if temperature > temperature_threshold:
                fan(True)
                blink_led(status_led, 3, 0.2)  # Fast blink
                print("Fan ON")
            elif temperature <= temperature_threshold - 2:
                fan(False)
                blink_led(status_led, 1, 1.0)  # Slow blink
                print("Fan OFF")
            time.sleep(10)  # Wait before next reading
        print("Fan management thread terminated")

async def main():
    global temperature_value, temperature_threshold
    temperature_threshold = load_threshold()
    sensor = qwiic_bme280.QwiicBme280()
    if not sensor.begin():
        print("Could not connect to BME280 sensor. Check wiring.")
        return
    # Connect to Wi-Fi
    connection = False
    connection_timeout = 10
    blink_led(status_led, 3, 0.1)
    while not connection:
            connection = connect_to_wifi()
            connection_timeout -= 1
            if connection_timeout == 0:
                print('Could not connect to Wi-Fi, exiting')
                reset()
    # Set up socket and start listening
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen()
    print('Listening on', addr)

    # Initialize variables
    temperature_value = 0

    while True:
        # blink_led(status_led, 2, 0.1)
        if not connection:
            break # exit if no connection

        try:
            conn, addr = s.accept()
            print('Got a connection from', addr)
            
            # Receive and parse the request
            request = conn.recv(1024)
            request = str(request)
            print('Request content = %s' % request)

            try:
                request = request.split()[1]
                print('Request:', request)
            except IndexError:
                pass
            
            # Process the request and update variables
            if request == '/temp_up?':
                temperature_threshold += 1
                store_threshold(temperature_threshold)
                print(f"Temperature threshold increased to {temperature_threshold} C")
            elif request == '/temp_down?':
                temperature_threshold -= 1
                store_threshold(temperature_threshold)
                print(f"Temperature threshold decreased to {temperature_threshold} C") 
            elif request == '/value?':
                temperature_value = get_temperature(sensor)

            # Generate HTML response
            response = webpage()  

            # Send the HTTP response and close the connection
            conn.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
            conn.send(response)
            conn.close()

        except OSError as e:
            conn.close()
            print('Connection closed')


if __name__ == "__main__":
    # Create an Event Loop
    loop = asyncio.get_event_loop()
    # Create a task to run the main function
    loop.create_task(main())
    sensor = qwiic_bme280.QwiicBme280()
    if not sensor.begin():
        print("Could not connect to BME280 sensor. Check wiring.")
    _thread.start_new_thread(manage_fan, ())
    print("Fan management thread started")
    try:
        # Run the event loop indefinitely
        loop.run_forever()
    except Exception as e:
        print('Error occurred: ', e)
    except KeyboardInterrupt:
        print('Program Interrupted by the user')
        terminateThread = True
        loop.stop()