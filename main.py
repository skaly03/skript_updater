from machine import Pin, I2C, ADC
from mcp4725 import MCP4725
from hw_emu import dac
import _thread
import mqtt_async
import asyncio
import network
import urequests
import random
import mywlan
import json
import time

# init a global dictionary for useage in multiple functions
glob = {
    # HW-variables
    'dac_ds': None,
    'dac_gs': None,
    'led': None,
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
    'mac_addr': None
    }

async def register_callback(topic, msg, retained, qos, dup):
    global glob
    client = glob['register_client']
    mac_addr = glob['mac_addr']
    
    topic = topic.decode('utf-8')
    msg = msg.decode('utf-8')
    print(f'Nachricht empfangen: Topic={topic}, Nachricht={msg}')

    try:
        if topic == glob['topic_prefix'] + f'/register_done/{mac_addr}':
            glob['board_id'] = msg
        
        if topic == glob['topic_prefix'] + '/Status':
            await client.publish(glob['topic_prefix'] + '/Status/Messplatz', 'Messplatz 1 online'.encode('utf-8'))

    except KeyError as e:
        await client.publish('test/meas/lastError', 'fehlender Key in Daten'.encode('utf-8'))
        print('Fehlender Key')
    except Exception as e:
        await client.publish('test/meas/lastError', 'fatal data error - could not read data'.encode('utf-8'))
        print(f'Unerwarteter Fehler, {e}')
        raise

async def register_conn_callback(client):
    SUB_TOPIC_REGISTER = glob['topic_prefix'] + f'/register_done/{glob['mac_addr']}'
    await client.subscribe(SUB_TOPIC_REGISTER, 1)

async def register_message(register_client):
    global glob
    while not glob['board_id']:
        await register_client.publish(glob['topic_prefix'] + '/register/' + glob['mac_addr'], glob['mac_addr'].encode('utf-8'))
        await asyncio.sleep(10)

async def register_loop(register_client):
    while True:
        await asyncio.sleep(0.5)
        if glob['board_id'] != False:
            await register_client.disconnect()
            break

async def register_config():
    global glob
    register_config = glob['register_config']

    # provide a already enabled wifi interface to the config file -> line 67 ff
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    wlan_mac = wlan.config('mac')
    mac_addr = wlan_mac.hex(':')
    glob['mac_addr'] = mac_addr

    mywlan.connect()

    register_config['server'] = 'broker.hivemq.com'
    register_config['port'] = 1883
    register_config['client_id'] = mac_addr + '-r'
    register_config['ssid'] = 'iPhone von Tobi'
    register_config['wifi_pw'] = 'WlanPasswort3344!'
    register_config['interface'] = wlan
    register_config['clean'] = False
    register_config['keepalive'] = 30
    register_config['subs_cb'] = register_callback
    register_config['connect_coro'] = register_conn_callback


    register_client = mqtt_async.MQTTClient(register_config)
    glob['register_config'] = register_config
    glob['register_client'] = register_client
    await register_client.connect()

    print('client ready for registration')
    await asyncio.gather(register_loop(register_client), register_message(register_client))

asyncio.get_event_loop().run_until_complete(register_config())

# start of mainly used loop for mqtt communication and measurement
time.sleep(5) # to make sure to be disconnected from broker

async def init_hw():
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
    glob['led'] = Pin('LED', Pin.OUT)
    glob['btn_1'] = Pin(0, Pin.IN, Pin.PULL_UP)
    glob['btn_2'] = Pin(1, Pin.IN, Pin.PULL_UP)
    glob['btn_3'] = Pin(2, Pin.IN, Pin.PULL_UP)

# runs, if btn_3 is pressed
async def blink(led, board_id, btn_3):
    while True:
        if btn_3.value() == 0:
            board_id = int(board_id)
            for i in range(board_id):
                led.on()
                await asyncio.sleep(0.2)
                led.off()
                await asyncio.sleep(0.2)     
        await asyncio.sleep(5)

async def meas(topic_dict, value_dict, client):
    global glob
    # topic_list needs: topic_prefix/board_id/username/messung
    # additional arguments are needed:

    # for meas_type 1: single values for u_gs and u_ds; optional: Multi-factor
    # example: {'U_DS': 2.0, 'U_GS': 2.2, 'multi': 100}

    # for meas_type 2: single value for u_gs, list of u_ds[start, stop, step]
    # example: {'U_DS': [0, 3.0, 0.25], 'U_GS': 2.0}

    # for meas_type 3: single value for u_ds, list of u_gs[start, stop, step]
    # example: {'U_DS': 2.0, 'U_GS': [1.0, 2.0, 0.1]}

    # for meas_type 4: list of [start, step, stop] for both u_gs and u_ds is needed
    # example: {'U_DS': [0, 3.3, 0.1], 'U_GS': [1, 3, 0.5]}

    #    for element in ADC_Ib:
    #    multi = 110/47
    #    voltage = element / multi
    #    current = voltage / 8
    #    Ib.append(current)

    dac_ds = glob['dac_ds']
    dac_gs = glob['dac_gs']

    username = topic_dict['username']
    meas_type = topic_dict['meas_type']
    board_id = glob['board_id']
    
    adc_ds = ADC(Pin(26))
    adc_gs = ADC(Pin(27))
    adc_Ib = ADC(Pin(28))
    multi_Ib = 9800/4600
    adcMax = 2**16 # 16 Bit
    adcVDD = 3.3   # Volt
    U_1 = 4095/adcVDD # reference-value for dac's: is used to iterate over 4095 states for Voltages fom 0 to 3.3 V

    if meas_type == 'Single-Measurement':
        if value_dict.get('multi') != None:
            multi = value_dict['multi']
        else:
            multi = 1 # default value
        break_bool = False
        multi_lst_ds = []
        multi_lst_gs = []
        multi_lst_Ib = []
        for _ in range(multi):
            dac_gs.write(int(value_dict['U_GS'] * U_1))
            dac_ds.write(int(value_dict['U_DS'] * U_1))
            time.sleep(0.1) # do not use asyncio on purpose here to sustain that measurement
            adc_ds_value = adc_ds.read_u16() * adcVDD / adcMax
            adc_gs_value = adc_gs.read_u16() * adcVDD / adcMax
            adc_Ib_value = adc_Ib.read_u16() * adcVDD / adcMax
            Ib_current = (adc_Ib_value / multi_Ib) / 7.8
            if Ib_current > 0.1:
                break_bool = True
            multi_lst_ds.append(adc_ds_value)
            multi_lst_gs.append(adc_gs_value)
            multi_lst_Ib.append(Ib_current)
        av_ds = sum(multi_lst_ds) / len(multi_lst_ds)
        av_gs = sum(multi_lst_gs) / len(multi_lst_gs)
        av_Ib = sum(multi_lst_Ib) / len(multi_lst_Ib)
        return_dict = {'U_DS': av_ds, 'U_GS': av_gs, 'I_D': av_Ib, 'break_bool': break_bool}
    
    elif meas_type == 'Drain-Source-Sweep':
        break_bool = False
        adc_ds_list = []
        adc_gs_list = []
        adc_Ib_list = []
        ds_calculated_value = value_dict['U_DS'][0]
        dac_gs.write(int(value_dict['U_GS'] * U_1))
        while ds_calculated_value < value_dict['U_DS'][1]:
            dac_gs.write(int(value_dict['U_GS'] * U_1))
            dac_ds.write(int(ds_calculated_value * U_1))
            ds_calculated_value = ds_calculated_value + value_dict['U_DS'][2] # At this point, the step variable of the given list is added to the variable
            time.sleep(0.1) # Wait a little...
            adc_ds_value = adc_ds.read_u16() * adcVDD / adcMax
            adc_gs_value = adc_gs.read_u16() * adcVDD / adcMax
            adc_Ib_value = adc_Ib.read_u16() * adcVDD / adcMax
            Ib_current = (adc_Ib_value / multi_Ib) / 7.8
            if Ib_current > 0.1:
                break_bool = True
                break
            # Publish for every loop iteration
            await client.publish(glob['topic_prefix'] + f"/Einzeln/{username}/{board_id}/{meas_type}", {'U_DS': adc_ds_value, 'U_GS': adc_gs_value, 'I_D': Ib_current})
            # Now we want to add those variables to the created list variables above
            adc_ds_list.append(adc_ds_value)
            adc_gs_list.append(adc_gs_value)
            adc_Ib_list.append(Ib_current)
        return_dict = {'U_DS': adc_ds_list, 'U_GS': adc_gs_list, 'I_D': adc_Ib_list, 'break_bool': break_bool}

    elif topic_dict['meas_type'] == 'Gate-Source-Sweep':
        break_bool = False
        adc_ds_list = []
        adc_gs_list = []
        adc_Ib_list = []
        gs_calculated_value = value_dict['U_GS'][0]
        dac_ds.write(int(value_dict['U_DS'] * U_1))
        while gs_calculated_value < value_dict['U_GS'][1]:
            dac_gs.write(int(gs_calculated_value * U_1))
            gs_calculated_value = gs_calculated_value + value_dict['U_GS'][2] # At this point, the step variable of the given list is added to the variable
            time.sleep(0.1) # Wait a little...
            adc_ds_value = adc_ds.read_u16() * adcVDD / adcMax
            adc_gs_value = adc_gs.read_u16() * adcVDD / adcMax
            adc_Ib_value = adc_Ib.read_u16() * adcVDD / adcMax
            Ib_current = (adc_Ib_value / multi_Ib) / 7.8
            if Ib_current > 0.1:
                break_bool = True
                break
            # Publish for every loop iteration
            await client.publish(glob['topic_prefix'] + f"/Einzeln/{username}/{board_id}/{meas_type}", {'U_DS': adc_ds_value, 'U_GS': adc_gs_value, 'I_D': Ib_current})
            # Now we want to add those variables to the created list variables above
            adc_ds_list.append(adc_ds_value)
            adc_gs_list.append(adc_gs_value)
            adc_Ib_list.append(Ib_current)
        return_dict = {'U_DS': adc_ds_list, 'U_GS': adc_gs_list, 'I_D': adc_Ib_list, 'break_bool': break_bool}
    
    elif topic_dict['meas_type'] == 'Combined-Sweep':
        break_bool = False
        return_dict = {}
        main_ds_list = []
        main_gs_list = []
        main_Ib_list = []
        ds_calculated_value = value_dict['U_DS'][0]
        gs_calculated_value = value_dict['U_GS'][0]
        while gs_calculated_value < value_dict['U_GS'][1]:
            # we need to make sure that all our used list in those loops are ready for new data
            adc_ds_list = []
            adc_gs_list = []
            adc_Ib_list = []
            dac_gs.write(int(gs_calculated_value * U_1))
            while ds_calculated_value < value_dict['U_DS'][1]:
                dac_ds.write(int(ds_calculated_value * U_1))
                ds_calculated_value = ds_calculated_value + value_dict['U_DS'][2] # At this point, the step variable of the given list is added to the variable
                time.sleep(0.1) # Wait a little...
                adc_ds_value = adc_ds.read_u16() * adcVDD / adcMax
                adc_gs_value = adc_gs.read_u16() * adcVDD / adcMax
                adc_Ib_value = adc_Ib.read_u16() * adcVDD / adcMax
                Ib_current = (adc_Ib_value / multi_Ib) / 7.8
                if Ib_current > 0.1:
                    break_bool = True
                    break
                # Publish for every loop iteration
                await client.publish(glob['topic_prefix'] + f"/Einzeln/{username}/{board_id}/{meas_type}", {'U_DS': adc_ds_value, 'U_GS': adc_gs_value, 'I_D': Ib_current})
                # Now we want to add those variables to the created list variables above
                adc_ds_list.append(adc_ds_value)
                adc_gs_list.append(adc_gs_value)
                adc_Ib_list.append(Ib_current)
            # we need to save those measured values before the loop starts again
            main_ds_list.append(adc_ds_list)
            main_gs_list.append(adc_gs_list)
            main_Ib_list.append(adc_Ib_list)
            # update and reset those values to ensure measurement-sweep
            gs_calculated_value = gs_calculated_value + value_dict['U_GS'][2]
            ds_calculated_value = value_dict['U_DS'][0]
        return_dict = {'U_DS': main_ds_list, 'U_GS': main_gs_list, 'I_D': main_Ib_list, 'break_bool': break_bool}
    else:
        return 'unknown measurement type'
    # sustain output low if the measurement is done
    dac_gs.write(0)
    dac_ds.write(0)

    #data_dict = {
    #    "username": topic_list[2],
    #    "board_id": int(glob['board_id']),
    #    "meas_type": topic_list[3],
    #    "U_DS": [2.0],
    #    "U_GS": [2.2],
    #    "I_D": [70]
    #}
    #await asyncio.sleep(5)
    #return data_dict
    
    return return_dict 

async def main_callback(topic, msg, retained, qos, dup):
    global glob
    client = glob['main_client']
    topic = topic.decode('utf-8')
    topic_list = topic.split('/')
    msg = msg.decode('utf-8')
    print(f'Nachricht empfangen: Topic={topic}, Nachricht={msg}')
    
    
    if len(topic_list) == 4 and topic_list[1] == glob['board_id']:
        await client.publish(glob['topic_prefix'] + f'/Zustand_Messplatz/{glob["board_id"]}', 'busy'.encode('utf-8'))
        msg = json.loads(msg)
        topic_dict = {
            'username': topic_list[2],
            'meas_type': topic_list[3]
        }
        if glob['dac_gs'] and glob['dac_ds']:
            result = await meas(topic_dict, msg, client)
        else:
            result = dac(topic_dict, msg)
        if result == 'unknown measurement type':
            await client.publish(glob['topic_prefix'] + f'/Paket/{topic_list[2]}/{glob["board_id"]}/{topic_list[3]}', result.encode('utf-8'))
        else:
            result = json.dumps(result)
            await client.publish(glob['topic_prefix'] + f'/Paket/{topic_list[2]}/{glob["board_id"]}/{topic_list[3]}', result.encode('utf-8'))
        await client.publish(glob['topic_prefix'] + f'/Zustand_Messplatz/{glob["board_id"]}', 'ready'.encode('utf-8'))
    
    elif topic == glob['topic_prefix'] + '/Status':
        await client.publish(glob['topic_prefix'] + f'/Status/Messplatz_{glob["board_id"]}', 'online status confirmed'.encode('utf-8'))
    
    elif topic == glob['topic_prefix'] + '/Zustand_Messplatz':
        await client.publish(glob['topic_prefix'] + f'/Zustand_Messplatz/{glob["board_id"]}', 'ready'.encode('utf-8'))
    
    elif topic == glob['topic_prefix'] + '/update':
        await updater()
        machine.reset()

async def main_conn_callback(client):
    SUB_TOPIC_MEAS = glob['topic_prefix'] + '/' + glob['board_id'] + '/+/+'
    SUB_TOPIC_CONDITION = glob['topic_prefix'] + '/Zustand_Messplatz'
    SUB_TOPIC_STATUS = glob['topic_prefix'] + '/Status'
    SUB_TOPIC_UPDATE = glob['topic_prefix'] + '/update'

    await client.subscribe(SUB_TOPIC_MEAS, 1)
    await client.subscribe(SUB_TOPIC_STATUS, 1)
    await client.subscribe(SUB_TOPIC_UPDATE, 1)
    await client.subscribe(SUB_TOPIC_CONDITION, 1)
    print('main-sub done')

async def main():
    global glob
    main_config = glob['main_config']
    # for now: if last-will is defined: rpi pico will lose its connection to the broker: dead socket - needs to be fixed for the purpose below
    # mqtt_async.config['will'] = mqtt_async.MQTTMessage(f'{glob["topic_prefix"]}/Zustand_Messplatz/{glob["board_id"]}', 'offline')
    main_config['server'] = 'broker.hivemq.com'
    main_config['port'] = 1883
    main_config['client_id'] = glob['mac_addr']
    main_config['ssid'] = 'iPhone von Tobi'
    main_config['wifi_pw'] = 'WlanPasswort3344!'
    main_config['interface'] = network.WLAN(network.STA_IF)
    main_config['clean'] = False
    main_config['keepalive'] = 30
    main_config['subs_cb'] = main_callback
    main_config['connect_coro'] = main_conn_callback
    main_config['client_id'] = glob['mac_addr']


    main_client = mqtt_async.MQTTClient(main_config)
    glob['main_config'] = main_config
    glob['main_client'] = main_client
    
    await init_hw()
    await main_client.connect()
    print('client ready')
    await main_client.publish(glob['topic_prefix'] + f'/Zustand_Messplatz/{glob["board_id"]}', 'ready'.encode('utf-8'))
    #connTask = asyncio.create_task(check_connection())
    blink_task = asyncio.create_task(blink(glob['led'], glob['board_id'], glob['btn_3']))
    mqttTask = asyncio.create_task(mqtt_task())
    await asyncio.gather(blink_task, mqttTask)

async def mqtt_task():
    while True:
        await asyncio.sleep(0.5)

# needs some further improvement...
async def check_connection():
    global glob
    client = mqtt_async.MQTTClient(glob['main_config'])
    if client._proto and client._proto.isconnected():
        await asyncio.sleep(glob['main_config']['keepalive'])
    else:
        print('please wait, we got a problem here...')
        try:
            client.connect()
            print('reconnection successful')
        except Exception as e:
            print('We got some bigger problems...')
            mywlan.connect(force_reconnect=True)
            client.connect()

# new function to remotely change the currently running script. Command via mqtt
async def updater():
    url = 'https://raw.githubusercontent.com/skaly03/skript_updater/main/main.py'
    r = urequests.get(url)
    with open('main.py', 'w') as file:
        file.write(r.text)
    time.sleep(1)

asyncio.get_event_loop().run_until_complete(main())
