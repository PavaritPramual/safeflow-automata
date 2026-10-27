# A: runtime automata definition

Policy: `smart-home-declarative-v1`; SHA256: `eebde030b13ac0ad43dfc9b941345ec062058e34d284d18129d2ad91d76248da`

Generated from JSON. Proposal transitions do not change state. Observed transitions follow actual effects.

| Machine | Edge | Phase | From | To | Guard | Outcome |
|---|---|---|---|---|---|---|
| R1 | R1.BothOff.human | proposal | BothOff | BothOff | `(source == "human")` | human_bypass |
| R1 | R1.BothOff.deny | proposal | BothOff | BothOff | `((source == "ai") && (((event.device == "air_conditioner") && (event.mode == "cool") && heater) &#124;&#124; ((event.device == "heater") && (event.mode == "on") && ac)))` | block |
| R1 | R1.BothOff.allow | proposal | BothOff | BothOff | `((source == "ai") && !((((event.device == "air_conditioner") && (event.mode == "cool") && heater) &#124;&#124; ((event.device == "heater") && (event.mode == "on") && ac))))` | allow |
| R1 | R1.Cooling.human | proposal | Cooling | Cooling | `(source == "human")` | human_bypass |
| R1 | R1.Cooling.deny | proposal | Cooling | Cooling | `((source == "ai") && (((event.device == "air_conditioner") && (event.mode == "cool") && heater) &#124;&#124; ((event.device == "heater") && (event.mode == "on") && ac)))` | block |
| R1 | R1.Cooling.allow | proposal | Cooling | Cooling | `((source == "ai") && !((((event.device == "air_conditioner") && (event.mode == "cool") && heater) &#124;&#124; ((event.device == "heater") && (event.mode == "on") && ac))))` | allow |
| R1 | R1.Heating.human | proposal | Heating | Heating | `(source == "human")` | human_bypass |
| R1 | R1.Heating.deny | proposal | Heating | Heating | `((source == "ai") && (((event.device == "air_conditioner") && (event.mode == "cool") && heater) &#124;&#124; ((event.device == "heater") && (event.mode == "on") && ac)))` | block |
| R1 | R1.Heating.allow | proposal | Heating | Heating | `((source == "ai") && !((((event.device == "air_conditioner") && (event.mode == "cool") && heater) &#124;&#124; ((event.device == "heater") && (event.mode == "on") && ac))))` | allow |
| R1 | R1.BothOn.human | proposal | BothOn | BothOn | `(source == "human")` | human_bypass |
| R1 | R1.BothOn.deny | proposal | BothOn | BothOn | `((source == "ai") && (((event.device == "air_conditioner") && (event.mode == "cool") && heater) &#124;&#124; ((event.device == "heater") && (event.mode == "on") && ac)))` | block |
| R1 | R1.BothOn.allow | proposal | BothOn | BothOn | `((source == "ai") && !((((event.device == "air_conditioner") && (event.mode == "cool") && heater) &#124;&#124; ((event.device == "heater") && (event.mode == "on") && ac))))` | allow |
| R1 | R1.BothOff.observed.BothOff | observed | BothOff | BothOff | `((!(ac) && !(heater)) && (((event.name == "hold") && (event.device == null) && (event.mode == null)) &#124;&#124; ((event.name == "set_device") && (event.device == "air_conditioner") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "heater") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "ventilation_fan") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "ventilation_fan") && (event.mode == "on")) &#124;&#124; ((event.name == "set_device") && (event.device == "light") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "light") && (event.mode == "on"))))` | observe |
| R1 | R1.BothOff.observed.Cooling | observed | BothOff | Cooling | `((ac && !(heater)) && (((event.name == "set_device") && (event.device == "air_conditioner") && (event.mode == "cool"))))` | observe |
| R1 | R1.BothOff.observed.Heating | observed | BothOff | Heating | `((!(ac) && heater) && (((event.name == "set_device") && (event.device == "heater") && (event.mode == "on"))))` | observe |
| R1 | R1.Cooling.observed.Cooling | observed | Cooling | Cooling | `((ac && !(heater)) && (((event.name == "hold") && (event.device == null) && (event.mode == null)) &#124;&#124; ((event.name == "set_device") && (event.device == "air_conditioner") && (event.mode == "cool")) &#124;&#124; ((event.name == "set_device") && (event.device == "heater") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "ventilation_fan") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "ventilation_fan") && (event.mode == "on")) &#124;&#124; ((event.name == "set_device") && (event.device == "light") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "light") && (event.mode == "on"))))` | observe |
| R1 | R1.Cooling.observed.BothOff | observed | Cooling | BothOff | `((!(ac) && !(heater)) && (((event.name == "set_device") && (event.device == "air_conditioner") && (event.mode == "off"))))` | observe |
| R1 | R1.Cooling.observed.BothOn | observed | Cooling | BothOn | `((ac && heater) && (((event.name == "set_device") && (event.device == "heater") && (event.mode == "on"))))` | observe |
| R1 | R1.Heating.observed.Heating | observed | Heating | Heating | `((!(ac) && heater) && (((event.name == "hold") && (event.device == null) && (event.mode == null)) &#124;&#124; ((event.name == "set_device") && (event.device == "air_conditioner") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "heater") && (event.mode == "on")) &#124;&#124; ((event.name == "set_device") && (event.device == "ventilation_fan") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "ventilation_fan") && (event.mode == "on")) &#124;&#124; ((event.name == "set_device") && (event.device == "light") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "light") && (event.mode == "on"))))` | observe |
| R1 | R1.Heating.observed.BothOn | observed | Heating | BothOn | `((ac && heater) && (((event.name == "set_device") && (event.device == "air_conditioner") && (event.mode == "cool"))))` | observe |
| R1 | R1.Heating.observed.BothOff | observed | Heating | BothOff | `((!(ac) && !(heater)) && (((event.name == "set_device") && (event.device == "heater") && (event.mode == "off"))))` | observe |
| R1 | R1.BothOn.observed.BothOn | observed | BothOn | BothOn | `((ac && heater) && (((event.name == "hold") && (event.device == null) && (event.mode == null)) &#124;&#124; ((event.name == "set_device") && (event.device == "air_conditioner") && (event.mode == "cool")) &#124;&#124; ((event.name == "set_device") && (event.device == "heater") && (event.mode == "on")) &#124;&#124; ((event.name == "set_device") && (event.device == "ventilation_fan") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "ventilation_fan") && (event.mode == "on")) &#124;&#124; ((event.name == "set_device") && (event.device == "light") && (event.mode == "off")) &#124;&#124; ((event.name == "set_device") && (event.device == "light") && (event.mode == "on"))))` | observe |
| R1 | R1.BothOn.observed.Heating | observed | BothOn | Heating | `((!(ac) && heater) && (((event.name == "set_device") && (event.device == "air_conditioner") && (event.mode == "off"))))` | observe |
| R1 | R1.BothOn.observed.Cooling | observed | BothOn | Cooling | `((ac && !(heater)) && (((event.name == "set_device") && (event.device == "heater") && (event.mode == "off"))))` | observe |
| R2 | R2.FirstUse.human | proposal | FirstUse | FirstUse | `(source == "human")` | human_bypass |
| R2 | R2.FirstUse.deny | proposal | FirstUse | FirstUse | `((source == "ai") && ((event.device == "air_conditioner") && (event.mode == "cool") && !(ac) && (elapsed != null) && (elapsed < rest_s)))` | block |
| R2 | R2.FirstUse.allow | proposal | FirstUse | FirstUse | `((source == "ai") && !(((event.device == "air_conditioner") && (event.mode == "cool") && !(ac) && (elapsed != null) && (elapsed < rest_s))))` | allow |
| R2 | R2.FirstUse.observed.FirstUse | observed | FirstUse | FirstUse | `(elapsed == null)` | observe |
| R2 | R2.FirstUse.observed.Resting | observed | FirstUse | Resting | `((elapsed != null) && (elapsed < rest_s))` | observe |
| R2 | R2.FirstUse.observed.Ready | observed | FirstUse | Ready | `((elapsed != null) && (elapsed >= rest_s))` | observe |
| R2 | R2.Resting.human | proposal | Resting | Resting | `(source == "human")` | human_bypass |
| R2 | R2.Resting.deny | proposal | Resting | Resting | `((source == "ai") && ((event.device == "air_conditioner") && (event.mode == "cool") && !(ac) && (elapsed != null) && (elapsed < rest_s)))` | block |
| R2 | R2.Resting.allow | proposal | Resting | Resting | `((source == "ai") && !(((event.device == "air_conditioner") && (event.mode == "cool") && !(ac) && (elapsed != null) && (elapsed < rest_s))))` | allow |
| R2 | R2.Resting.observed.Resting | observed | Resting | Resting | `((elapsed != null) && (elapsed < rest_s))` | observe |
| R2 | R2.Resting.observed.Ready | observed | Resting | Ready | `((elapsed != null) && (elapsed >= rest_s))` | observe |
| R2 | R2.Ready.human | proposal | Ready | Ready | `(source == "human")` | human_bypass |
| R2 | R2.Ready.deny | proposal | Ready | Ready | `((source == "ai") && ((event.device == "air_conditioner") && (event.mode == "cool") && !(ac) && (elapsed != null) && (elapsed < rest_s)))` | block |
| R2 | R2.Ready.allow | proposal | Ready | Ready | `((source == "ai") && !(((event.device == "air_conditioner") && (event.mode == "cool") && !(ac) && (elapsed != null) && (elapsed < rest_s))))` | allow |
| R2 | R2.Ready.observed.Resting | observed | Ready | Resting | `((elapsed != null) && (elapsed < rest_s))` | observe |
| R2 | R2.Ready.observed.Ready | observed | Ready | Ready | `((elapsed != null) && (elapsed >= rest_s))` | observe |

## Clock reset rules

- `rest` uses `elapsed`; reset to zero when `(before.ac && !(after.ac))`, then add elapsed simulation time.
