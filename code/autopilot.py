import math
import time
import krpc

turn_start_altitude = 250 # начало наклона
turn_end_altitude = 40000  # конец когда наклон будет горизонтальный
target_altitude = 327000 
target_periapsis = 181000

conn = krpc.connect(name='Launch into orbit')
vessel = conn.space_center.active_vessel
obt_frame = vessel.orbit.body.non_rotating_reference_frame
srf_frame = vessel.orbit.body.reference_frame

# Установка потоков для отслеживания данных
ut = conn.add_stream(getattr, conn.space_center, 'ut')
altitude = conn.add_stream(getattr, vessel.flight(), 'mean_altitude')
height_above_surface = conn.add_stream(getattr, vessel.flight(), 'bedrock_altitude')
apoapsis = conn.add_stream(getattr, vessel.orbit, 'apoapsis_altitude')
periapsis = conn.add_stream(getattr, vessel.orbit, 'periapsis_altitude')
stage_1_resources = vessel.resources_in_decouple_stage(stage=6, cumulative=False)
first_stage_fuel = conn.add_stream(stage_1_resources.amount, 'LiquidFuel')

start_time = ut()

f = open("res.txt", mode='w')
# Настройки перед запуском
vessel.control.sas = False
vessel.control.rcs = False
vessel.control.throttle = 1.0
time.sleep(5)
print('3...')
time.sleep(1)
print('2...')
time.sleep(1)
print('1...')
time.sleep(1)
print('Поехали!')

# Активируем первую ступень
vessel.control.activate_next_stage()
vessel.auto_pilot.engage()
vessel.auto_pilot.target_pitch_and_heading(90, 90)

first_stage_separated = False
second_stage_separated = False
fairing_seperated = False

i = 0
frequency = 1
turn_angle = 0
while True:

    # Gravity turn
    if altitude() > turn_start_altitude and altitude() < turn_end_altitude:
        frac = ((altitude() - turn_start_altitude) /
                (turn_end_altitude - turn_start_altitude))
        new_turn_angle = frac * 90
        if abs(new_turn_angle - turn_angle) > 0.3:
            turn_angle = new_turn_angle
            vessel.auto_pilot.target_pitch_and_heading(90 - turn_angle + 0.1, 90)

    # Отделение первой ступени
    if not first_stage_separated:
        # print(f'{str(speed())} {str(ut() - start_time)}')
        if first_stage_fuel() < 0.1:
            vessel.control.activate_next_stage()
            first_stage_separated = True
            print('Первая ступень отделена')
    if i > frequency:
        obt_speed = vessel.flight(obt_frame).speed
        srf_speed = vessel.flight(srf_frame).speed
        f.write(f'{str(height_above_surface())} {str(ut())}\n')
        print(f'{str(height_above_surface())} {str(ut() - start_time)}')
        i = 0
    # отделение обтекателя на 70 км
    if not fairing_seperated:
        if height_above_surface() > 70000:
            vessel.control.activate_next_stage()
            fairing_seperated = True
            print("Обтекатель отделен")

    # Уменьшаем тягу, когда подлетает к апогею
    if apoapsis() >= target_altitude * 0.9:
        print('Приблежение к апогею')
        break
    i += 1
    time.sleep(0.01)

# Отключение двигателей при достижении апогея
vessel.control.throttle = 0.25
while apoapsis() < target_altitude:
    if i > frequency:
        obt_speed = vessel.flight(obt_frame).speed
        srf_speed = vessel.flight(srf_frame).speed
        f.write(f'{str(height_above_surface())} {str(ut())}\n')
        print(f'{str(height_above_surface())} {str(ut())}')
        i = 0
    time.sleep(0.01)
    i += 1
    pass
print('Апогей достигнут')
f.close()
vessel.control.throttle = 0.0

time.sleep(0.5)
# отделение 2 ступени
if not second_stage_separated:
    vessel.control.activate_next_stage()
    second_stage_separated = True

time.sleep(5)

# Планируем маневр с помощью формулы удельной орбитальной энергии
print('Планируем маневр')
mu = vessel.orbit.body.gravitational_parameter
r = vessel.orbit.apoapsis
a1 = vessel.orbit.semi_major_axis
a2 = r
v1 = math.sqrt(mu * ((2. / r) - (1. / a1)))
v2 = math.sqrt(mu * ((2. / r) - (1. / a2)))
delta_v = v2 - v1
node = vessel.control.add_node(
    ut() + vessel.orbit.time_to_apoapsis, prograde=delta_v)

# Считаем время работы двигателей по формуле Циалковского
F = vessel.available_thrust
Isp = vessel.specific_impulse * 9.82
m0 = vessel.mass
m1 = m0 / math.exp(delta_v / Isp)
flow_rate = F / Isp
burn_time = (m0 - m1) / flow_rate

# Направление корабля
print('Ориентация корабля')
vessel.auto_pilot.reference_frame = node.reference_frame
vessel.auto_pilot.target_direction = (0, 1, 0)
vessel.auto_pilot.wait()

# Ожидание до маневра
print('Ожидание маневра')
burn_ut = ut() + vessel.orbit.time_to_apoapsis - (burn_time / 2.)
lead_time = 5
conn.space_center.warp_to(burn_ut - lead_time)

# Исполнение
print('Готовы начать маневр')
time_to_apoapsis = conn.add_stream(getattr, vessel.orbit, 'time_to_apoapsis')
while time_to_apoapsis() - (burn_time / 2.) > 0:
    pass
print('Маневр начался')
vessel.control.throttle = 1.0
while periapsis() < target_periapsis:
    time.sleep(0.01)

vessel.control.throttle = 0.0
node.remove()
print('Маневр завершен')
vessel.auto_pilot.disengage()

time.sleep(0.5)
vessel.control.activate_next_stage()

print('Начинаем торможение')
vessel.control.sas = True
vessel.control.activate_next_stage()

while periapsis() >= -282000:
    time.sleep(0.001)
vessel.control.throttle = 0

while altitude() >= 35000:
    time.sleep(0.001)

print('Отделение последней ступени')
vessel.control.activate_next_stage()
while altitude() >= 30000:
    time.sleep(0.001)

while altitude() >= 7000:
    time.sleep(0.001)
vessel.control.activate_next_stage()
