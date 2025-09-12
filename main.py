from machine import Pin, I2C, ADC
from mcp4725 import MCP4725
from hw_emu import dac as emu
from sync_time import ntp_sync
import _thread
import mqtt_async
import asyncio
import network
import urequests
import array
import random
import mywlan
import json
import time
import gc
import os

from ulogging import RotatingLogger
logger = RotatingLogger(
    name="main",
    console_level=RotatingLogger.DEBUG,
    file_level=RotatingLogger.WARNING,
    filename="logging.txt",
    max_size=50*1024
)
# init a config to be edited by users
config = {
    'mqtt_server': 'broker.hivemq.com',
    'mqtt_port': 1883,
}
# init a global dictionary for useage in multiple functions
glob = {
    # HW-variables
    'dac_ds': None,
    'dac_gs': None,
    'led_board': None,
    'led_1': None,
    'led_2': None,
    'led_3': None,
    'btn_1': None,
    'btn_2': None,
    'btn_3': None,
    # MQTT-based variables
    'topic_prefix': 'tobi_felix_hm_fk06',
    'sub_topic': '/Status',
    'main_config': mqtt_async.config,
    'main_client': None,
    'register_config': mqtt_async.config,
    'register_client': None,
    # Board-specific variables
    'board_id': False,
    'mac_addr': None, 
    'wlan': None,
    # for measurement: arrays
    'gs_array': array.array('f', [0.0] * 5000),
    'ds_array': array.array('f', [0.0] * 5000),
    'ib_array': array.array('f', [0.0] * 5000),
    }
# ------------------------------------
#  MQTT: Start of registration process
# ------------------------------------

async def wifi_conn(wifi_request):
    """
    ### Wifi Management

    Works with an additional Python script `mywlan.py` that detects
    all networks in the vicinity and compares them with the SSIDs and
    passwords stored in the `mywlan_ssids.json` file. If a known network
    is found, the script attempts to establish a connection.

        Args:
            wifi_request (bool or str)
            * to establish a wifi connection:       True
            * to disconnect from a wifi connection: False
            * to re-establish the connection:       'reconnect'
        Returns:
            None
        Note:
            The scripts `mywlan.py` and `mywlan_ssids.json` or another network manager should be
            present and correctly configured.
    """
    global glob
    wlan = glob['wlan']
    if wifi_request == True and not wlan.isconnected():
            mywlan.connect()
            logger.info('wifi connection established')
    elif wifi_request == False and wlan.isconnected():
        mywlan.connect(force_disconnect=True)
        logger.info('wifi disconnected')
    elif wifi_request == 'reconnect' and wlan.isconnected():
        mywlan.connect(force_reconnect=True)
        logger.info('wifi reconnected')
    else:
        # requested already established/disconnected connection. Request will be ignored
        pass

async def broker_conn_loop(client):
    """
    ### Broker connection loop

    Loops around until the connection to the configured broker is established successfully.
    * First attempt: try to establish a connection
    * Second attempt: try reconnecting to the wifi and then establishing a connection to the broker

    The system will loop around those cases and try to connect until a connection is established.
    
        Args:
            client (client-object)
        Returns:
            None
        Note:
            Uses the wifi_conn() function
    """
    while client._state != 1:
        try:
            try:
                await client.connect()
            except Exception as e:
                logger.debug('Could not reach broker... reconnecting wifi...')
                await wifi_conn('reconnect')
                await client.connect()
        except Exception as e:
            logger.critical(f'could not connect to broker: {e}')
            asyncio.sleep(10)
            continue

async def register_conn_callback(client):
    """
    Is called when a connection to the broker has been established.
        Args:
            * client (client-object)
        returns:
            None
    """
    # managing subscriptions...
    SUB_TOPIC_REGISTER = f"{glob['topic_prefix']}/board_register_done/{glob['mac_addr']}"
    await client.subscribe(SUB_TOPIC_REGISTER, 1)
    logger.debug('register topic subscription succesful')

async def register_callback(topic, msg, retained, qos, dup):
    """
    ### MQTT-Callback of the registration client

    Is called when a message is recieved via MQTT on the subscribed topics.
    Takes the arguments `msg` and `topic` which are filtered further. These
    callbacks then trigger the desired functions.
    
        Args:
            * topic
            * msg
            * retained
            * qos
            * dup
        Returns:
            All returns are published via MQTT
        Exceptions:
            All exceptions within the callbacks will trigger an Error and terminate this function.
    """
    global glob
    # client = glob['register_client']
    # mac_addr = glob['mac_addr']
    
    topic = topic.decode('utf-8')
    msg = msg.decode('utf-8')
    logger.debug(f'recieved mqtt message at {topic}, Payload: {msg}')

    try:
        # measuring station recieves its board_id here, regsitration within the database
        if topic == f"{glob['topic_prefix']}/board_register_done/{glob['mac_addr']}":
            glob['board_id'] = msg
            logger.debug('board_id set')

    except Exception as e:
        logger.warning(f'error in register_callback: {e}')

async def register_message(register_client):
    """
    Sends a message via MQTT every 10 seconds in a loop until the board registration is complete.
        Args:
            register_client (client-object)
        Returns:
            None
    """
    global glob
    while not glob['board_id']: # loop ends when a board_id has been assigned
        # if the database or manager is not yet online
        topic = f"{glob['topic_prefix']}/board_register/{glob['mac_addr']}"
        payload = glob['mac_addr'].encode('utf-8')
        await register_client.publish(topic, payload)
        logger.debug(f'Publish at {topic}, Payload: {payload}')
        await asyncio.sleep(10)

async def register_loop(register_client):
    """
    Main loop of the registration process. Will terminate when the process is done.
        Args:
            register_client (client-object)
        Returns:
            None
    """
    while True:
        await asyncio.sleep(0.5)
        if glob['board_id'] != False:
            logger.info('registration process complete, disconnecting from broker...')
            await register_client.disconnect()
            break

async def register_config():
    """
    Must be called from a asyncio-eventloop. Configures and controls the registration process.
    """
    global glob
    global config
    register_config = glob['register_config']

    # provide a already enabled wifi interface to the config file
    wlan = mywlan._init_wlan()
    wlan_mac = wlan.config('mac')
    mac_addr = wlan_mac.hex(':')
    glob['mac_addr'] = mac_addr
    glob['wlan'] = wlan
    await wifi_conn(True)
    try:
        ntp_sync()
    except:
        logger.warning('NTP time failed')

    register_config['server'] = config['mqtt_server']
    register_config['port'] = config['mqtt_port']
    register_config['client_id'] = mac_addr + '-r'
    register_config['interface'] = wlan
    register_config['clean'] = False
    register_config['keepalive'] = 30
    register_config['subs_cb'] = register_callback
    register_config['connect_coro'] = register_conn_callback
    # skipping internal wifi management, using my own...
    register_config['wifi_coro'] = wifi_conn
    # an error will occur if those strings are not set -> must be something else then None
    register_config['ssid'] = 'must_be_any_string'
    register_config['wifi_pw'] = 'must_be_any_string'

    register_client = mqtt_async.MQTTClient(register_config)
    glob['register_config'] = register_config
    glob['register_client'] = register_client
    await broker_conn_loop(register_client)
    logger.debug('connection to broker successful')
    logger.info('start registration process')
    await asyncio.gather(register_loop(register_client), register_message(register_client))

asyncio.get_event_loop().run_until_complete(register_config())

# start of mainly used loop for mqtt communication and measurement
time.sleep(5) # to make sure to be disconnected from broker
gc.collect()

# ----------------------------
# MQTT: start of main function
# ----------------------------

async def init_hw():
    """
    Initialises the desired hardware, if available.
    """
    global glob
    i2c = I2C(id=0, scl=Pin(17), sda=Pin(16), freq=400000)
    try:
        glob['dac_ds'] = MCP4725(i2c=i2c, address=98)
        glob['dac_gs'] = MCP4725(i2c=i2c, address=99)
        glob['dac_ds'].write(0)
        glob['dac_gs'].write(0)
    except Exception as e:
        print('no hardware found, change into emulation mode')
        glob['dac_ds'] = None
        glob['dac_gs'] = None
    glob['btn_1'] = Pin(0, Pin.IN, Pin.PULL_UP)
    glob['btn_2'] = Pin(1, Pin.IN, Pin.PULL_UP)
    glob['btn_3'] = Pin(2, Pin.IN, Pin.PULL_UP)
    glob['led_1'] = Pin(3, Pin.OUT)
    glob['led_2'] = Pin(4, Pin.OUT)
    glob['led_3'] = Pin(5, Pin.OUT)
    glob['led_board'] = Pin('LED', Pin.OUT)
    logger.debug('init_hw done')

# runs, if btn_3 is pressed
async def blink(led, board_id, btn_3):
    """
    Function for identifying a board or the board_id via an LED
        Args:
            * led (Pin-object)
            * board_id (str)
            * btn (Pin-object)
    """
    while True:
        if btn_3.value() == 0:
            board_id = int(board_id)
            for i in range(board_id):
                led.on()
                await asyncio.sleep(0.2)
                led.off()
                await asyncio.sleep(0.2)     
        await asyncio.sleep(2)

async def reserve_buffer(size, buffer):
    start = 0
    end = start + size
    if end > len(buffer):
        raise MemoryError("Kein freier Speicher mehr im globalen Puffer")
    return start, end

async def reshape_buffer(buffer_slice: array.array):
    start_idx = 0
    reshaped = []
    for idx, value in enumerate(buffer_slice):
            if value == 0.0: # no value found
                pass
            elif value == 5.0: # stop value found (will be written if break_bool = True)
                if idx > start_idx:
                    reshaped.append(buffer_slice[start_idx:idx])
                start_idx = idx+1
            elif value == 10.0: # initial ending value
                break
    return reshaped


async def meas(topic_dict: dict, value_dict: dict, client):
    """
    ### Main measurement funciton. Description tba

    topic_list needs topic_prefix/board_id/username/messung
    #### additional arguments are needed

        * for meas_type 1: single values for u_gs and u_ds; optional: Multi-factor
            * example: {'U_DS': 2.0, 'U_GS': 2.2, 'multi': 100}

        * for meas_type 2: single value for u_gs, list of u_ds[value_1, value_2, ...]
            * example: {'U_DS': [0, 3.0, 0.25], 'U_GS': 2.0}

        * for meas_type 3: single value for u_ds, list of u_gs[value_1, value_2, ...]
            * example: {'U_DS': 2.0, 'U_GS': [1.0, 2.0, 0.1]}

        * for meas_type 4: list of [start, step, stop] for both u_gs and u_ds is needed
            * example: {'U_DS': [value_1, value_2, ...], 'U_GS': [value_1, value_2, ...]}
    
    """

    global glob
    dac_ds = glob['dac_ds']
    dac_gs = glob['dac_gs']

    username = topic_dict['username']
    meas_type = topic_dict['meas_type']
    time_stamp = topic_dict['time_stamp']
    board_id = glob['board_id']
    
    adc_ds = ADC(Pin(26))
    adc_gs = ADC(Pin(27))
    adc_Ib = ADC(Pin(28))
    multi_Ib = 9800/4600
    adcMax = 2**16 # 16 Bit
    adcVDD = 3.3   # Volt
    U_1 = 4095/adcVDD # reference-value for dac's: is used to iterate over 4095 states for Voltages fom 0 to 3.3 V
    
    topic = f"{glob['topic_prefix']}/Einzeln/{username}/{time_stamp}/{board_id}/{meas_type}"
    break_bool = False

    if meas_type == 'Single-Measurement':
        multi = value_dict.get('multi', 1)
        break_bool = False
        dac_gs.write(int(value_dict['U_GS'] * U_1))
        dac_ds.write(int(value_dict['U_DS'] * U_1))
        adc_ds_sum, adc_gs_sum, Ib_current_sum = 0, 0, 0
        for _ in range(multi):
            adc_ds_sum += adc_ds.read_u16() * adcVDD / adcMax
            adc_gs_sum += adc_gs.read_u16() * adcVDD / adcMax
            adc_opv_value = adc_Ib.read_u16() * adcVDD / adcMax
            Ib_current_sum += (adc_opv_value / multi_Ib) / 7.8
            if (adc_opv_value / multi_Ib) / 7.8 > 0.1: # checks if any Ib_current > 0.1 A
                break_bool = True
                return {'U_DS': '', 'U_GS': '', 'I_D': '', 'break_bool': break_bool}
            # calculate average values
        ds_av_value = adc_ds_sum / multi
        gs_av_value = adc_gs_sum / multi
        Ib_av_value = Ib_current_sum / multi
        return_dict = {'U_DS': ds_av_value, 'U_GS': gs_av_value, 'I_D': Ib_av_value, 'break_bool': break_bool}
        gc.collect()
    
    elif meas_type == 'Drain-Source-Sweep':
        multi = value_dict.get('multi', 1)
        needed_size = len(value_dict['U_DS'])
        start, end = await reserve_buffer(needed_size, glob['ds_array']) # any buffer to check if there is enough space for all values
        idx = start # = 0
        dac_gs.write(int(value_dict['U_GS'] * U_1))
        for ds_value in value_dict['U_DS']:
            dac_ds.write(int(ds_value * U_1))
            time.sleep(0.1) # Wait a little...
            # init / reset sum variables
            adc_ds_sum, adc_gs_sum, Ib_current_sum = 0, 0, 0
            for _ in range(multi):
                adc_ds_sum += adc_ds.read_u16() * adcVDD / adcMax
                adc_gs_sum += adc_gs.read_u16() * adcVDD / adcMax
                adc_opv_value = adc_Ib.read_u16() * adcVDD / adcMax
                Ib_current_sum += (adc_opv_value / multi_Ib) / 7.8
                if (adc_opv_value / multi_Ib) / 7.8 > 0.1: # checks if any Ib_current > 0.1 A
                    break_bool = True
                    break
            # calculate average values
            if break_bool:
                break
            # calculate average values
            ds_av_value = adc_ds_sum / multi
            gs_av_value = adc_gs_sum / multi
            Ib_av_value = Ib_current_sum / multi
            # save those variables to the corresponding arrays
            glob['ds_array'][idx] = ds_av_value
            glob['gs_array'][idx] = gs_av_value
            glob['ib_array'][idx] = Ib_av_value
            idx += 1
            # Publish for every loop iteration
            payload = json.dumps({'U_DS': ds_av_value, 'U_GS': gs_av_value, 'I_D': Ib_av_value}).encode('utf-8')
            await client.publish(topic, payload)
            logger.debug(f'Publish at {topic}, Payload: {payload}')

        main_ds_list = list(glob['ds_array'][start:idx])
        main_gs_list = list(glob['gs_array'][start:idx])
        main_ib_list = list(glob['ib_array'][start:idx])
        return_dict = {'U_DS': main_ds_list, 'U_GS': main_gs_list, 'I_D': main_ib_list, 'break_bool': break_bool}
        logger.debug(f'Bevore allocation: {gc.mem_free()/1000} kB')
        gc.collect()
        logger.debug(f'After allocation: {gc.mem_free()/1000} kB')

    elif topic_dict['meas_type'] == 'Gate-Source-Sweep':
        multi = value_dict.get('multi', 1)
        needed_size = len(value_dict['U_GS'])
        start, end = await reserve_buffer(needed_size, glob['ds_array']) # any buffer to check if there is enough space for all values
        idx = start # = 0
        dac_ds.write(int(value_dict['U_DS'] * U_1))
        for gs_value in value_dict['U_GS']:
            dac_gs.write(int(gs_value * U_1))
            time.sleep(0.1) # Wait a little...
            # init / reset sum variables
            adc_ds_sum, adc_gs_sum, Ib_current_sum = 0, 0, 0
            for _ in range(multi):
                adc_ds_sum += adc_ds.read_u16() * adcVDD / adcMax
                adc_gs_sum += adc_gs.read_u16() * adcVDD / adcMax
                adc_opv_value = adc_Ib.read_u16() * adcVDD / adcMax
                Ib_current_sum += (adc_opv_value / multi_Ib) / 7.8
                if (adc_opv_value / multi_Ib) / 7.8 > 0.1: # checks if any Ib_current > 0.1 A
                    break_bool = True
                    break
            if break_bool:
                    break
            # calculate average values
            ds_av_value = adc_ds_sum / multi
            gs_av_value = adc_gs_sum / multi
            Ib_av_value = Ib_current_sum / multi
            # save those variables to the corresponding arrays
            glob['ds_array'][idx] = ds_av_value
            glob['gs_array'][idx] = gs_av_value
            glob['ib_array'][idx] = Ib_av_value
            idx += 1
            # Publish for every loop iteration
            payload = json.dumps({'U_DS': ds_av_value, 'U_GS': gs_av_value, 'I_D': Ib_av_value}).encode('utf-8')
            await client.publish(topic, payload)
            logger.debug(f'Publish at {topic}, Payload: {payload}')

        main_ds_list = list(glob['ds_array'][start:idx])
        main_gs_list = list(glob['gs_array'][start:idx])
        main_ib_list = list(glob['ib_array'][start:idx])
        return_dict = {'U_DS': main_ds_list, 'U_GS': main_gs_list, 'I_D': main_ib_list, 'break_bool': break_bool}
        logger.debug(f'Bevore allocation: {gc.mem_free()/1000} kB')
        gc.collect()
        logger.debug(f'After allocation: {gc.mem_free()/1000} kB')
    
    elif topic_dict['meas_type'] == 'Combined-Sweep':
        multi = value_dict.get('multi', 1)
        outer_len = len(value_dict['U_GS'])
        inner_len = len(value_dict['U_DS'])
        needed_size = outer_len * inner_len
        start, end = await reserve_buffer(needed_size, glob['ds_array']) # any buffer to check if there is enough space for all values
        idx = start # = 0
        # for gs_value in value_dict['U_GS']:
        for gs_value in value_dict['U_GS']:
            break_flag = False
            # we need to make sure that all of our used list in those loops are ready for new data
            dac_gs.write(int(gs_value * U_1))
            for ds_value in value_dict['U_DS']:
                dac_ds.write(int(ds_value * U_1))
                time.sleep(0.1) # Wait a little...
                # init / reset sum variables
                adc_ds_sum, adc_gs_sum, Ib_current_sum = 0, 0, 0
                for _ in range(multi):
                    adc_ds_sum += adc_ds.read_u16() * adcVDD / adcMax
                    adc_gs_sum += adc_gs.read_u16() * adcVDD / adcMax
                    adc_opv_value = adc_Ib.read_u16() * adcVDD / adcMax
                    Ib_current_sum += (adc_opv_value / multi_Ib) / 7.8
                    if (adc_opv_value / multi_Ib) / 7.8 > 0.1: # checks if any Ib_current > 0.1 A
                        break_bool = True
                        break_flag = True
                        break
                if break_flag:
                    glob['ds_array'][idx] = 5.0
                    glob['gs_array'][idx] = 5.0
                    glob['ib_array'][idx] = 5.0
                    idx += 1
                    break
                # calculate average values
                ds_av_value = adc_ds_sum / multi
                gs_av_value = adc_gs_sum / multi
                Ib_av_value = Ib_current_sum / multi
                # save those variables to the corresponding arrays
                glob['ds_array'][idx] = ds_av_value
                glob['gs_array'][idx] = gs_av_value
                glob['ib_array'][idx] = Ib_av_value
                idx += 1
                # Publish for every loop iteration
                payload = json.dumps({'U_DS': ds_av_value, 'U_GS': gs_av_value, 'I_D': Ib_av_value, 'U_GS_selected': gs_value}).encode('utf-8')
                await client.publish(topic, payload)
                logger.debug(f'Publish at {topic}, Payload: {payload}')
            # we need to mark the end of a loop iteration
            glob['ds_array'][idx] = 5.0
            glob['gs_array'][idx] = 5.0
            glob['ib_array'][idx] = 5.0
            idx += 1
            logger.debug(f'Bevore allocation: {gc.mem_free()/1000} kB')
            gc.collect()
            logger.debug(f'After allocation: {gc.mem_free()/1000} kB')
        glob['ds_array'][idx] = 10.0
        glob['gs_array'][idx] = 10.0
        glob['ib_array'][idx] = 10.0
        main_ds_list = await reshape_buffer(glob['ds_array'][start:idx])
        main_gs_list = await reshape_buffer(glob['gs_array'][start:idx])
        main_ib_list = await reshape_buffer(glob['ib_array'][start:idx])
        return_dict = {'U_DS': main_ds_list, 'U_GS': main_gs_list, 'I_D': main_ib_list, 'break_bool': break_bool}
    else:
        return 'unknown measurement type'
    # sustain output low if the measurement is done
    dac_gs.write(0)
    dac_ds.write(0)
    logger.debug('meas_task complete')
    return return_dict 

async def main_callback(topic, msg, retained, qos, dup):
    global glob
    client = glob['main_client']
    topic = topic.decode('utf-8')
    topic_list = topic.split('/')
    msg = msg.decode('utf-8')
    logger.debug(f'recieved mqtt message at {topic}, Payload: {msg}')

    condition_topic = f"{glob['topic_prefix']}/Zustand_Messplatz/{glob["board_id"]}"
    
    try:
        if len(topic_list) == 5 and topic_list[1] == glob['board_id']:
            payload = 'busy'.encode('utf-8')
            await client.publish(condition_topic, payload)
            logger.debug(f'Publish at {condition_topic}, Payload: {payload}')

            msg = json.loads(msg)
            topic_dict = {
                'username': topic_list[2],
                'time_stamp': topic_list[3],
                'meas_type': topic_list[4]
            }
            # checks whether hardware is available or whether emulation is required
            if glob['dac_gs'] and glob['dac_ds']:
                result = await meas(topic_dict, msg, client)
            else:
                result = emu(topic_dict, msg)
            
            if result != 'unknown measurement type':
                result = json.dumps(result)
            
            data_topic = f"{glob['topic_prefix']}/Paket/{topic_list[2]}/{topic_list[3]}/{glob["board_id"]}/{topic_list[4]}"
            payload = result.encode('utf-8')
            await client.publish(data_topic, payload)
            logger.debug(f'Publish at {data_topic}, Payload: {payload}')
            
            payload = 'ready'.encode('utf-8')
            await client.publish(condition_topic, payload)
            logger.debug(f'Publish at {condition_topic}, Payload: {payload}')
        
        elif topic == f"{glob['topic_prefix']}/Status":
            status_topic = f"{topic}/Messplatz_{glob["board_id"]}"
            payload = 'online status confirmed'.encode('utf-8')
            await client.publish(status_topic, payload)
            logger.debug(f'Publish at {status_topic}, Payload: {payload}')

        elif topic == f"{glob['topic_prefix']}/Zustand_Messplatz":
            payload = 'ready'.encode('utf-8')
            await client.publish(condition_topic, payload)
            logger.debug(f'Publish at {condition_topic}, Payload: {payload}')
        
        elif topic == f"{glob['topic_prefix']}/update":
            try: # First case: Message contains a dictionary with filename and foldername that needs to be updated
                msg = json.loads(msg)
            except:# Second case: Message contains a string with filename
                pass
            update_topic = f"{glob['topic_prefix']}/debug/{glob["board_id"]}"

            if type(msg) == dict and len(msg) == 2:
                payload = f'updating {msg['file']}'.encode('utf-8')
                await client.publish(update_topic, payload)
                logger.debug(f'Publish at {update_topic}, Payload: {payload}')

                await updater(msg['file'], msg['folder'])
                logger.warning(f'file {msg['file']} updated')

            elif type(msg) == str:
                payload = f'updating {msg}'.encode('utf-8')
                await client.publish(update_topic, payload)
                logger.debug(f'Publish at {update_topic}, Payload: {payload}')

                await updater(msg)
                logger.warning(f'file {msg} updated')
            else:
                return # do nothing
            
            machine.reset()

    except Exception as e:
        debug_topic = f"{glob['topic_prefix']}/debug/{glob["board_id"]}"
        payload = f'An Error occured: {e}'.encode('utf-8')
        await client.publish(debug_topic, payload)
        logger.debug(f'Publish at {debug_topic}, Payload: {payload}')

        payload = 'ready'.encode('utf-8')
        await client.publish(condition_topic, payload)
        logger.debug(f'Publish at {condition_topic}, Payload: {payload}')
        logger.error(f'Error detected: {e}')

    gc.collect()

async def main_conn_callback(client):
    SUB_TOPIC_MEAS      = f"{glob['topic_prefix']}/{glob['board_id']}/+/+/+"
    SUB_TOPIC_CONDITION = f"{glob['topic_prefix']}/Zustand_Messplatz"
    SUB_TOPIC_STATUS    = f"{glob['topic_prefix']}/Status"
    SUB_TOPIC_UPDATE    = f"{glob['topic_prefix'] }/update"

    await client.subscribe(SUB_TOPIC_MEAS, 1)
    await client.subscribe(SUB_TOPIC_STATUS, 1)
    await client.subscribe(SUB_TOPIC_UPDATE, 1)
    await client.subscribe(SUB_TOPIC_CONDITION, 1)
    logger.debug('main subscription succesful')

async def main():
    global glob
    global config
    main_config = glob['main_config']
    # for now: if last-will is defined: rpi pico will lose its connection to the broker: dead socket - needs to be fixed for the purpose below
    main_config['will'] = mqtt_async.MQTTMessage(f'{glob["topic_prefix"]}/Zustand_Messplatz/{glob["board_id"]}', 'offline')
    main_config['server'] = config['mqtt_server']
    main_config['port'] = config['mqtt_port']
    main_config['client_id'] = glob['mac_addr']
    main_config['interface'] = network.WLAN(network.STA_IF)
    main_config['clean'] = False
    main_config['keepalive'] = 100
    main_config['response_time'] = 30
    main_config['subs_cb'] = main_callback
    main_config['connect_coro'] = main_conn_callback
    main_config['wifi_coro'] = wifi_conn
    # an error will occur if those strings are not set -> must be something else then None
    main_config['ssid'] = 'must_be_any_string'
    main_config['wifi_pw'] = 'must_be_any_string'


    main_client = mqtt_async.MQTTClient(main_config)
    glob['main_config'] = main_config
    glob['main_client'] = main_client
    
    await init_hw()
    await broker_conn_loop(main_client)
    logger.info('Connection to broker succesfully established')

    condition_topic = f"{glob['topic_prefix']}/Zustand_Messplatz/{glob["board_id"]}"
    payload = 'ready'.encode('utf-8')
    await main_client.publish(condition_topic, payload)
    logger.debug(f'Publish at {condition_topic}, Payload: {payload}')
    logger.debug(f'Free RAM: {gc.mem_free()/1000} kB')

    #connTask = asyncio.create_task(check_connection())
    blink_task = asyncio.create_task(blink(glob['led_board'], glob['board_id'], glob['btn_3']))
    mqttTask = asyncio.create_task(mqtt_task())
    await asyncio.gather(blink_task, mqttTask)

async def mqtt_task():
    while True:
        await asyncio.sleep(0.5)

# needs some further improvement... may no longer be needed
async def check_connection():
    global glob
    client = (glob['main_client'])
    if client._state == 1:
        await asyncio.sleep(glob['main_config']['keepalive'])
    elif client._state == 2:
        try:
            try:
                client.connect()
            except Exception as e:
                mywlan.connect(force_reconnect=True)
                client.connect()
        except:
            config = glob['main_config']
            main_client = mqtt_async.MQTTClient(config)
            await broker_conn_loop(main_client)

# new function to remotely change currently running script. Command via mqtt
async def updater(file_name, folder=None):
    url = f'https://raw.githubusercontent.com/skaly03/skript_updater/main/{file_name}'
    r = urequests.get(url)
    if folder:
        if folder not in os.listdir():
            os.mkdir(folder)
        with open(f'{folder}/{file_name}', 'w') as file:
            file.write(r.text)
        time.sleep(1)
    else:
        with open(file_name, 'w') as file:
            file.write(r.text)
        time.sleep(1)

asyncio.get_event_loop().run_until_complete(main())
