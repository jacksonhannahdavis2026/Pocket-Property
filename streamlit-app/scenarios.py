from dataclasses import replace

from underwriting import PropertyInputs, calculate


def build_scenarios(base_inputs: PropertyInputs):
    scenarios = {}

    scenario_names = ["Aggressive", "Base", "Conservative"]

    for name in scenario_names:
        scenario_inputs = replace(base_inputs, case_scenario=name)
        scenarios[name] = calculate(scenario_inputs)

    return scenarios
