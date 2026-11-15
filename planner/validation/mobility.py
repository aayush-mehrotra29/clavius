"""NASA Glenn-inspired rigid-wheel discrepancy benchmark, not a soil model.

The published wheel/load/velocity conditions are retained. Contact here is a
rigid plane with the application's declared Coulomb friction. The benchmark
measures the missing deformable-soil response rather than fitting it away.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import numpy as np

POLICY = {
    'id': 'clavius-trec-rigid-contact-discrepancy-v4',
    'gravity_m_s2': 9.81, 'duration_s': 20., 'steady_start_s': 10.,
    'friction_coefficient': .7, 'timestep_s': .00003125,
    'refined_timestep_s': .000015625, 'refinement_source_indices': [1, 7, 16],
    'maximum_translation_error_m_s': .002,
    'maximum_angular_speed_relative_error': .01,
    'maximum_normal_load_relative_error': .05,
    'traction_rmse_target_deg': 5., 'maximum_traction_error_target_deg': 10.,
    'refinement_mean_traction_target_deg': 1.,
    'target_scope': 'Predeclared development targets, not published experimental uncertainties or a mission accuracy bound.',
    'calibration_fit_performed': False,
    'lunar_validation_established': False,
    'rig_controller': 'Velocity feedback with previous-step generalized contact-force compensation; no fit to experimental traction points.',
    'translation_velocity_gain_n_s_m': 10000.,
    'spin_velocity_gain_nm_s_rad': 1000.,
}


def wheel_omega(translation_m_s, radius_m, slip):
    if not all(math.isfinite(x) for x in [translation_m_s, radius_m, slip]) or radius_m <= 0 or slip >= 1:
        raise ValueError('Invalid controlled wheel speed inputs')
    return translation_m_s / (radius_m*(1-slip))


def traction_angle(drawbar_pull_n, normal_load_n):
    if not all(math.isfinite(x) for x in [drawbar_pull_n, normal_load_n]) or normal_load_n <= 0:
        raise ValueError('Invalid traction force or normal load')
    return math.degrees(math.atan(drawbar_pull_n/normal_load_n))


def model_xml(rig, dt, friction):
    radius, width = rig['wheel_outer_radius_m'], rig['wheel_width_m']
    height, thickness, count = rig['grouser_height_m'], rig['grouser_tangential_width_m'], rig['grouser_count']
    mass = rig['normal_loaded_mass_kg']/2
    root = ET.Element('mujoco', model='TREC published geometry on a declared rigid plane')
    ET.SubElement(root, 'compiler', angle='radian')
    ET.SubElement(root, 'option', timestep=str(dt), gravity='0 0 -9.81', integrator='implicitfast', iterations='100', tolerance='1e-10')
    default = ET.SubElement(root, 'default')
    ET.SubElement(default, 'geom', friction=f'{friction} .005 .0001', condim='3', solref='.01 1', solimp='.99 .99 .001')
    world = ET.SubElement(root, 'worldbody')
    ET.SubElement(world, 'geom', name='rigid_ground', type='plane', size='20 2 .1')
    carriage = ET.SubElement(world, 'body', name='guided_carriage', pos=f'0 0 {radius+.005}')
    ET.SubElement(carriage, 'joint', name='translation', type='slide', axis='1 0 0')
    ET.SubElement(carriage, 'inertial', mass=str(mass), pos='0 0 0', diaginertia='.1 .1 .1')
    axle = ET.SubElement(carriage, 'body', name='free_vertical_axle')
    ET.SubElement(axle, 'joint', name='vertical', type='slide', axis='0 0 1')
    ET.SubElement(axle, 'inertial', mass=str(mass), pos='0 0 0', diaginertia='.1 .1 .1')
    wheel = ET.SubElement(axle, 'body', name='wheel')
    ET.SubElement(wheel, 'joint', name='spin', type='hinge', axis='0 1 0')
    # Declared envelope-cylinder inertia; not a flight wheel's measured tensor.
    transverse = mass*(3*radius**2+width**2)/12
    polar = mass*radius**2/2
    ET.SubElement(wheel, 'inertial', mass=str(mass), pos='0 0 0', diaginertia=f'{transverse} {polar} {transverse}')
    ET.SubElement(wheel, 'geom', name='wheel_core', type='cylinder', size=f'{radius-height} {width/2}', quat='.7071067811865476 .7071067811865476 0 0')
    for index in range(count):
        angle = 2*math.pi*index/count
        center = radius-height/2
        ET.SubElement(wheel, 'geom', name=f'grouser_{index}', type='box', size=f'{thickness/2} {width/2} {height/2}', pos=f'{center*math.sin(angle)} 0 {center*math.cos(angle)}', quat=f'{math.cos(angle/2)} 0 {math.sin(angle/2)} 0')
    actuators = ET.SubElement(root, 'actuator')
    # Actual tracking errors are measured; failed control invalidates comparison.
    ET.SubElement(actuators, 'velocity', name='translation_control', joint='translation', kv=str(POLICY['translation_velocity_gain_n_s_m']))
    ET.SubElement(actuators, 'velocity', name='spin_control', joint='spin', kv=str(POLICY['spin_velocity_gain_nm_s_rad']))
    return ET.tostring(root, encoding='unicode')


def simulate(rig, slip, dt=POLICY['timestep_s'], duration=POLICY['duration_s'], friction=POLICY['friction_coefficient'], cancel=lambda: False):
    import mujoco
    xml = model_xml(rig, dt, friction)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    speed = rig['translation_m_s']
    omega = wheel_omega(speed, rig['wheel_outer_radius_m'], slip)
    trans_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'translation')
    spin_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'spin')
    vertical_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'vertical')
    trans_dof, spin_dof = model.jnt_dofadr[trans_id], model.jnt_dofadr[spin_id]
    data.qvel[trans_dof], data.qvel[spin_dof] = speed, omega
    data.ctrl[:] = [speed, omega]
    rows, steady = [], []
    force = np.zeros(6)
    for step in range(round(duration/dt)):
        if step % 1000 == 0 and cancel():
            raise InterruptedError('Mobility benchmark cancelled')
        data.ctrl[0] = speed-data.qfrc_constraint[trans_dof]/POLICY['translation_velocity_gain_n_s_m']
        data.ctrl[1] = omega-data.qfrc_constraint[spin_dof]/POLICY['spin_velocity_gain_nm_s_rad']
        old_speed = float(data.qvel[trans_dof])
        mujoco.mj_step(model, data)
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            raise ValueError('Nonfinite native wheel state')
        normal, longitudinal = 0., 0.
        for index in range(data.ncon):
            mujoco.mj_contactForce(model, data, index, force)
            normal += max(0., float(force[0]))
            contact = data.contact[index]
            # MuJoCo's contact frame rows are its normal/tangent basis, and
            # positive force acts on geom2. Ground is geom0 in this fixture.
            direction = 1 if contact.geom1 == 0 else -1
            longitudinal += direction*float((contact.frame.reshape(3,3).T @ force[:3])[0])
        acceleration = (float(data.qvel[trans_dof])-old_speed)/dt
        # Newton balance for the whole moving rig: external drawbar load equals
        # contact traction minus inertial acceleration. Do not use the stale
        # explicit velocity-servo force as the drawbar measurement.
        moving_mass = 1.5*rig['normal_loaded_mass_kg']
        drawbar = longitudinal-moving_mass*acceleration
        row = [float(data.time), float(data.qvel[trans_dof]), float(data.qvel[spin_dof]), drawbar, normal, float(data.actuator_force[1]), float(data.qpos[model.jnt_qposadr[vertical_id]]), longitudinal, acceleration, -float(data.actuator_force[0])]
        if data.time >= POLICY['steady_start_s']:
            steady.append(row)
        if step % max(1, round(.02/dt)) == 0 or step == round(duration/dt)-1:
            rows.append(row)
    if not steady:
        raise ValueError('Benchmark must include the declared steady window')
    values = np.asarray(steady)
    mean = values.mean(axis=0)
    load = rig['normal_loaded_mass_kg']*POLICY['gravity_m_s2']
    mean_slip = 1-mean[1]/(mean[2]*rig['wheel_outer_radius_m'])
    controls = {
        'translation_tracking': bool(abs(mean[1]-speed) <= POLICY['maximum_translation_error_m_s']),
        'rotation_tracking': bool(abs(mean[2]-omega)/abs(omega) <= POLICY['maximum_angular_speed_relative_error']),
        'normal_load': bool(abs(mean[4]-load)/load <= POLICY['maximum_normal_load_relative_error']),
    }
    return {'requested_slip_fraction': slip, 'mean_actual_slip_fraction': mean_slip, 'mean_translation_m_s': mean[1], 'mean_angular_velocity_rad_s': mean[2], 'mean_drawbar_pull_n': mean[3], 'drawbar_pull_standard_deviation_n': float(values[:,3].std()), 'mean_normal_force_n': mean[4], 'nominal_normal_load_n': load, 'mean_traction_slope_deg': traction_angle(mean[3], load), 'mean_reported_servo_torque_nm': mean[5], 'mean_vertical_displacement_m': mean[6], 'mean_contact_longitudinal_n': mean[7], 'mean_horizontal_acceleration_m_s2': mean[8], 'mean_explicit_servo_force_n': mean[9], 'drawbar_measurement': 'World contact traction minus whole-rig translational inertia; explicit implicit-integrator servo force is diagnostic only.', 'controls': controls, 'controls_passed': all(controls.values()), 'timestep_s': dt, 'trace_columns': ['t_s', 'translation_m_s', 'omega_rad_s', 'drawbar_pull_n', 'normal_force_n', 'explicit_servo_spin_torque_nm', 'axle_vertical_displacement_m', 'contact_longitudinal_n', 'horizontal_acceleration_m_s2', 'explicit_servo_force_n']}, np.asarray(rows), xml


def comparison(rows):
    errors = np.asarray([row['mean_traction_slope_deg']-row['published_traction_slope_deg'] for row in rows])
    rmse, maximum = float(np.sqrt(np.mean(errors**2))), float(np.max(np.abs(errors)))
    return {'point_count': len(rows), 'traction_rmse_deg': rmse, 'maximum_abs_traction_error_deg': maximum, 'mean_bias_deg': float(errors.mean()), 'all_rig_controls_passed': all(row['controls_passed'] for row in rows), 'traction_development_targets_met': rmse <= POLICY['traction_rmse_target_deg'] and maximum <= POLICY['maximum_traction_error_target_deg'], 'lunar_validation_established': False}
