*** SPICE Deck created by TSMC ADC Timing Team ***
* DONT_TOUCH_PINS
* CELL XOR4MDLIMZD4BWP130HPNPN3P48CPD | REL_PIN A2 | REL_PIN_DIR rise | CONSTR_PIN Z | CONSTR_PIN_DIR rise | OUTPUT_PIN Z |  | WHEN notA1_notA3_notA4 | OUTPUT_LOAD 0.002096 | TEMPLATE_PINLIST A1 A2 A3 A4 Z | ARC_TYPE combinational | VECTOR xRxxR
* REL_PIN_SLEWS 0.000001 0.000699 0.002096 0.004889 0.010476 0.021649 0.043996 0.088690 | CONSTR_PIN_SLEWS 0.0019 0.0611 0.1791 0.4155 0.8881 1.8334 3.7240 7.9962 | MAX_SLEW 7.9962
* TEMPLATE_DECK hack_template_v2/template__common_inpin_rise_delay_rise.sp

* SPICE options
.options RUNLVL=6 ACCURATE=1 BRIEF=1 autostop MODSRH=1 gmindc=1e-15 gmin=1e-15
.options sampling_method=sobol
.save level=none

* Waveform
.inc '/CAD/stdcell/DesignKits/Sponsor/Script/MCQC_automation/Template/std_wv_c651.spi'

* Model include file
.inc '/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/0-FMC_golden/gen_DECKs/ssgnp_0p450v_m40c_DECKs/delay/ssgnp_0p450v_m40c_cworst_CCworst_T.delay.inc'

* Netlist path
.inc '/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/0-FMC_golden/Collaterals/kits/base/3svt/Netlist/LPE_cworst_CCworst_T_m40c/XOR4MDLIMZD4BWP130HPNPN3P48CPD.spi'

* Library information
.param vdd_value = '0.450'
.param vss_value = 0
.temp -40

* Slew and load information
.param cl = '0.021649p'
.param rel_pin_slew = '1.8334n'

* Voltage and Output Load

VVDD VDD 0 'vdd_value'
VVSS VSS 0 'vss_value'
VVPP VPP 0 'vdd_value'
VVBB VBB 0 'vss_value'

* Output Load
CZ Z 0 'cl'

* Subckt Definition
X1 A1 A2 A3 A4 Z VDD VSS VPP VBB XOR4MDLIMZD4BWP130HPNPN3P48CPD

* Waveform timestamps
.param max_slew = '7.9962n'
.param related_pin_t01 = 200ns

* Pin definitions
VA1 A1 0 'vss_value'
VA3 A3 0 'vss_value'
VA4 A4 0 'vss_value'

* Unspecified pins



* Toggling pins
XVA2 A2 0 stdvs_rise VDD='vdd_value' slew='rel_pin_slew' t01='related_pin_t01'

* Measurements
.meas tran meas_delay trig v(A2) val = 'vdd_value/2' cross=1 targ v(Z) val='vdd_value/2' cross=1
.meas tran half_tt_out trig v(Z) val = 'vdd_value*0.3' cross=1 targ v(Z) val='vdd_value*0.7' cross=1
.meas tran meas_tt_out param='half_tt_out*2'

* Transient Sim Command
.tran 1p 5000n sweep monte=100000

.end
