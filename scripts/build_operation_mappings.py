"""Rebuild reviewed operation vocabulary and exact migrations from a frozen registry.

The grouping below is an explicit semantic decision table. Names are never clustered
by spelling. Re-running this tool does not inspect remote sources or call a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def parameter(kind="string", *, dimension=None, description=None):
    result = {"type": kind, "required": False}
    if dimension:
        result["dimension"] = dimension
    if description:
        result["description"] = description
    return result


COMMON_PARAMETERS = {
    "vessel": parameter("reference"),
    "duration_s": parameter("quantity", dimension="time"),
    "method": parameter(),
    "apparatus": parameter("reference"),
    "conditions": parameter("object"),
    "configuration": parameter("object", description="Reported object configuration; does not imply equipment ratings or an additional setup action."),
    "source_context": parameter("object", description="Reported provenance and contextual statements; no implied process action."),
    "reported_parameters": parameter("object", description="Source facts retained when no narrower parameter is established; never supplies missing facts."),
}


def operation(name, description, *, kind="action", domain="general", fields=None,
              preconditions=(), effects=(), capabilities=()):
    return {"name": name, "kind": kind, "domain": domain,
            "description": description,
            "parameters": {**COMMON_PARAMETERS, **(fields or {})},
            "preconditions": list(preconditions), "effects": list(effects),
            "capabilities": list(capabilities)}


Q = lambda dimension: parameter("quantity", dimension=dimension)
S = parameter
R = lambda: parameter("reference")
O = lambda: parameter("object")


def operations():
    """Professional concepts whose differences are expressed by typed parameters."""
    definitions = {
        "op.add": operation("Add", "Introduce material into a destination once. Independent mass, volume and molar readings describe the same portion, not extra additions.",
            fields={"reagent": S(), "alias": S(), "amount": Q("material_amount"), "mass": Q("mass"), "volume": Q("volume"), "substance_amount": Q("amount_of_substance"), "concentration": Q("concentration"), "equivalents": Q("relative_amount"), "relative_loading": Q("relative_amount"), "rate": Q("flow_rate"), "addition_order": S(), "distribution": O(), "components": O(), "initial_contents": O(), "role": S(), "formulation": S()},
            preconditions=["Material and destination may be unknown but must not be invented."], effects=["Introduces the reported portion into the destination inventory once."], capabilities=["material_delivery", "material_containment"]),
        "op.transfer": operation("Transfer", "Relocate material between locations; retain explicitly unknown source, destination and quantity.",
            fields={"from_vessel": R(), "to_vessel": R(), "amount": Q("material_amount"), "material": S(), "rate": Q("flow_rate"), "initial_contents": O(), "components": O(), "atmosphere": S()},
            effects=["Relocates the stated material; unknown quantities propagate unknown inventory."], capabilities=["material_transfer"]),
        "op.mix": operation("Mix", "Agitate materials using the stated mechanism. Stirring, shaking and vortexing remain distinct method values.",
            fields={"materials": S(), "rpm": Q("rotational_frequency"), "method": {"type": "string", "required": False, "known_values": ["stir", "shake", "vortex"], "open_vocabulary": True}, "temperature": Q("temperature"), "temp_C": Q("temperature"), "temperature_condition": S()},
            effects=["Agitates contents without implying material addition or successful dissolution."], capabilities=["agitation.{method}"]),
        "op.temperature": operation("SetTemperature", "Apply a stated thermal condition when a direction of temperature change is not established.",
            fields={"temp_C": Q("temperature"), "temperature": Q("temperature"), "temperature_scale": S(), "temperature_subject": S(), "ramp": O(), "thermal_condition": S(), "stir": S("boolean"), "rpm": Q("rotational_frequency")},
            effects=["Changes the explicitly targeted thermal condition; apparatus and sample temperatures remain distinct."], capabilities=["thermal_control"]),
        "op.heat": operation("Heat", "Supply thermal energy; method, energy input, reflux and apparatus conditions are parameters.",
            fields={"temp_C": Q("temperature"), "temperature": Q("temperature"), "temperature_scale": S(), "temperature_subject": S(), "energy_input": S(), "mode": S(), "thermal_condition": S(), "ramp": O(), "power_W": Q("power"), "atmosphere": S(), "mixing_condition": S()},
            effects=["Applies heating to the stated target without asserting measured equilibration."], capabilities=["thermal_heating", "energy_input.{energy_input}"]),
        "op.cool": operation("Cool", "Lower temperature; qualitative targets remain qualitative.",
            fields={"temp_C": Q("temperature"), "temperature": Q("temperature"), "temperature_scale": S(), "ramp": O()}, effects=["Lowers the targeted temperature without inventing an endpoint."], capabilities=["thermal_cooling"]),
        "op.hold_temperature": operation("HoldTemperature", "Maintain or expose an object to a reported thermal condition without inferring active control or sample equilibration.",
            fields={"temperature": Q("temperature"), "temp_C": Q("temperature"), "temperature_subject": S(), "thermal_condition": S(), "target_equipment": R(), "concurrent_action": R()}, effects=["Preserves the reported thermal exposure interval."], capabilities=["thermal_environment"]),
        "op.wait": operation("Wait", "Let the stated time elapse without implying any treatment.", effects=["Advances the reported interval once."]),
        "op.atmosphere": operation("Atmosphere", "Establish or describe a gas environment while preserving the reported mode; a context is not a purge.",
            fields={"gas": S(), "mode": S(), "pressure": Q("pressure"), "flow_rate": Q("flow_rate"), "cycle_count": S("integer"), "extent": S(), "contact_method": S()},
            effects=["Updates only the gas condition and establishment action explicitly reported."], capabilities=["gas_handling"]),
        "op.degas": operation("Degas", "Remove gas from material without inferring technique or atmosphere replacement.", fields={"material": S(), "gas": S(), "repetition_qualifier": S()}, effects=["Removes gas as reported."], capabilities=["degassing"]),
        "op.evacuate": operation("Evacuate", "Reduce pressure in the target without assuming a pressure or repeated cycles.", fields={"pressure": Q("pressure")}, effects=["Reduces pressure as reported."], capabilities=["vacuum"]),
        "op.seal": operation("Seal", "Close a vessel using the reported closure; closure implies no pressure rating.", fields={"closure": S(), "vessel_type": S()}, effects=["Sets the reported closure state."], capabilities=["vessel_closure"]),
        "op.separate": operation("Separate", "Separate phases while preserving which phase is retained and unresolved retention.", fields={"keep_phase": S(), "to_vessel": R(), "solvent": S()}, effects=["Partitions material into the reported retained and removed phases."], capabilities=["phase_separation"]),
        "op.filter": operation("Filter", "Filter material through the stated medium, preserving the retained fraction.", fields={"keep": S(), "to_vessel": R(), "through": S()}, effects=["Partitions solids and filtrate without inventing the retained fraction."], capabilities=["filtration"]),
        "op.evaporate": operation("Evaporate", "Remove volatile material by evaporation; concentration and dryness endpoints are distinct.", fields={"solvent": S(), "material_removed": S(), "pressure_mbar": Q("pressure"), "pressure": Q("pressure"), "pressure_condition": S(), "temperature": Q("temperature"), "temp_C": Q("temperature"), "endpoint": S()}, effects=["Removes volatile material only to the stated extent."], capabilities=["evaporation"]),
        "op.remove_material": operation("RemoveMaterial", "Remove material when the mechanism is not established; do not assume evaporation.", fields={"material": S(), "destination": R(), "extent": S()}, effects=["Removes the identified material by the stated or unknown mechanism."]),
        "op.dry": operation("Dry", "Remove moisture or residual volatile material using the reported drying mechanism.", fields={"material": S(), "bath": S(), "temperature": Q("temperature"), "temp_C": Q("temperature"), "pressure": Q("pressure"), "pressure_condition": S()}, effects=["Dries material without asserting complete dryness unless reported."], capabilities=["drying"]),
        "op.wash": operation("Wash", "Contact material with washing media; retain order, repetition and unresolved separation details.", fields={"material": S(), "solvent": S(), "amount": Q("material_amount"), "wash_count": S("integer"), "wash_media": S(), "amounts": S(), "sequence_or_combination": S(), "separation_method": S()}, effects=["Performs reported washing without implying a phase selection or collection route."], capabilities=["washing"]),
        "op.dissolve": operation("Dissolve", "Form a solution from the reported solutes and solvent without inventing addition order or mixing.", fields={"solvent": S(), "solvent_volume": Q("volume"), "solute_materials": S(), "components": O(), "solvent_volume_literal": S()}, effects=["Forms the reported solution; no separate addition is implied by this record alone."], capabilities=["solution_preparation"]),
        "op.suspend": operation("Suspend", "Disperse material in a liquid to form a suspension without assuming an agitation mechanism.", fields={"medium": S(), "material": S()}, effects=["Forms the reported suspension."], capabilities=["suspension_preparation"]),
        "op.contact": operation("Contact", "Bring specified materials into contact for a purpose without implying agitation or chemical success.", fields={"materials": S(), "metal_precursor": S(), "ligand": S(), "solvent": S(), "purpose": S()}, effects=["Establishes reported contact only."], capabilities=["material_containment"]),
        "op.adsorb": operation("Adsorb", "Adsorb material onto a support without inferring mixing or solvent removal.", fields={"material": S(), "support": S(), "support_amount": Q("material_amount"), "timing": S(), "subsequent_purification_medium": S()}, effects=["Associates material with the specified support."], capabilities=["adsorption"]),
        "op.chromatograph": operation("Chromatograph", "Separate material chromatographically; retain stationary phase, mobile phase, ratio basis and elution sequence.", fields={"material": S(), "stationary_phase": S(), "eluent": S(), "eluent_component": S(), "eluent_carrier": S(), "eluent_percentage": Q("fraction"), "percentage_basis": S(), "eluent_ratio": S(), "eluent_ratio_range": S(), "elution_sequence": S(), "eluent_program": S(), "first_eluent": S(), "second_eluent": S(), "first_eluent_grade": S(), "status": S()}, effects=["Performs the stated separation; unsuccessful attempts do not imply isolation."], capabilities=["chromatography"]),
        "op.purify": operation("Purify", "Purify by a reported method whose physical substeps are not otherwise specified.", fields={"to_vessel": R(), "procedure_reference": S()}, effects=["Represents the reported purification without fabricating substeps."], capabilities=["purification.{method}"]),
        "op.collect": operation("Collect", "Collect selected fractions without inferring pooling, volume or fraction numbers.", fields={"fraction_selection": S(), "destination": R()}, effects=["Collects the stated selected material."], capabilities=["fraction_collection"]),
        "op.load": operation("Load", "Load material onto an apparatus for a subsequent operation.", fields={"material": S(), "elution_sequence": S()}, effects=["Loads material without performing an additional separation."], capabilities=["material_loading"]),
        "op.elute": operation("Elute", "Perform an explicitly reported elution stage of a chromatographic separation.", fields={"material": S(), "stationary_phase": S(), "eluent": S(), "eluent_ratio": S(), "ratio_basis": S(), "elution_sequence": S()}, effects=["Elutes the associated separation once."], capabilities=["chromatography"]),
        "op.recrystallize": operation("Recrystallize", "Purify by recrystallization without expanding unreported dissolution, cooling or collection steps.", fields={"material": S(), "solvent": S(), "solvent_amount": Q("material_amount")}, effects=["Represents the reported recrystallization."], capabilities=["recrystallization"]),
        "op.position": operation("Position", "Position an object relative to equipment without transferring its contents.", fields={"target_equipment": R(), "target_temperature": Q("temperature"), "target_condition": S(), "relation": S()}, effects=["Changes physical placement, not material inventory or measured sample temperature."], capabilities=["apparatus_positioning"]),
        "op.configure_vessel": operation("ConfigureVessel", "Specify or prepare the vessel and environment exactly as reported; do not infer physical drying or purging.", fields={"vessel_type": S(), "capacity": Q("volume"), "environment": S(), "condition": S(), "location": S(), "annotation": S(), "drying_method": S()}, effects=["Establishes reported vessel configuration and initial context."], capabilities=["material_containment"]),
        "op.analyze": operation("Analyze", "Perform a reported analytical examination; sample preparation and measured outcomes remain separate facts.", fields={"sample": S(), "sample_amount": Q("material_amount"), "nucleus": S(), "internal_standard": S(), "internal_standard_amount": Q("material_amount"), "results": O()}, effects=["Performs reported analysis without prescribing an observed product or yield."], capabilities=["analysis.{method}"]),
        "op.monitor": operation("Monitor", "Monitor using the reported method and schedule without inventing sampling or a time origin.", fields={"reported_times": S(), "time_reference": S(), "sampling_protocol": S(), "results": O()}, effects=["Performs the stated monitoring schedule."], capabilities=["analysis.{method}"]),
        "op.measure": operation("Measure", "Perform an explicitly reported measurement without inventing an additional material charge.", fields={"material": S(), "mass": Q("mass"), "volume": Q("volume"), "substance_amount": Q("amount_of_substance")}, effects=["Produces the stated measurement."], capabilities=["measurement.{method}"]),
        "op.aspirate": operation("Aspirate", "Withdraw reported portions using a liquid handler; combination and count retain their reported basis.", fields={"source_material": S(), "components": S(), "volume_per_component": Q("volume"), "combination": S()}, effects=["Withdraws the stated portions and combines them only if reported."], capabilities=["liquid_aspiration"]),
        "op.discard": operation("Discard", "Discard material without inferring quenching or a disposal treatment.", fields={"material": S(), "destination": R(), "extent": S()}, effects=["Removes discarded material from retained inventory."], capabilities=["waste_collection"]),
        "op.stop": operation("StopReaction", "Represent explicitly stated cessation while keeping an unreported physical termination method unknown.", fields={"termination_statement": S()}, effects=["Stops the reported process; no cooling, quench, disposal or apparatus shutdown is inferred."]),
        "op.irradiate": operation("Irradiate", "Expose material to optical radiation; microwave heating remains Heat with microwave energy input.", fields={"wavelength_nm": Q("length"), "power_W": Q("power"), "color": S()}, effects=["Applies the stated optical exposure."], capabilities=["optical_irradiation"]),
        "op.sonicate": operation("Sonicate", "Apply ultrasonic energy with the reported conditions.", fields={"power_W": Q("power"), "frequency": Q("frequency")}, effects=["Applies ultrasound without assuming agitation equivalence."], capabilities=["ultrasound"]),
        "obs.observation": operation("RecordObservation", "Retain a reported observation without commanding it as a physical process.", kind="observation", fields={"observation": S(), "results": O(), "observation_type": S()}, effects=["Adds observation metadata; no physical-state effect."]),
        "obs.analysis": operation("RecordAnalysis", "Retain reported analytical findings without asserting acquisition or sample preparation.", kind="observation", fields={"sample": S(), "internal_standard": S(), "internal_standard_amount": Q("material_amount"), "results": O(), "observation_type": S()}, effects=["Adds analytical metadata; no material addition or analysis acquisition."]),
        "obs.product": operation("RecordProduct", "Retain reported product identity, quantity, yield, appearance and characterization as observations.", kind="observation", fields={"product": S(), "mass": Q("mass"), "substance_amount": Q("amount_of_substance"), "yield": Q("fraction"), "appearance": S(), "results": O()}, effects=["Adds reported outcome metadata; no isolation or material-state change."]),
        "obs.completion": operation("RecordCompletion", "Retain reported completion, progress or conversion without instructing a successful outcome.", kind="observation", fields={"assessment": S(), "conversion": Q("fraction"), "elapsed_time": Q("time"), "results": O()}, effects=["Adds completion metadata; no chemical transformation is commanded."]),
        "obs.disposition": operation("RecordDisposition", "Retain abandonment, omission or experiment disposition without inferring physical termination.", kind="observation", fields={"disposition": S(), "statement": S(), "termination_method": S(), "observation": S()}, effects=["Adds disposition metadata; no quench, cooling, disposal or shutdown."]),
        "obs.charge": operation("RecordChargeProperties", "Retain supplementary quantities of an associated charge without counting another addition.", kind="observation", fields={"reagent": S(), "mass": Q("mass"), "volume": Q("volume"), "substance_amount": Q("amount_of_substance"), "addition_order": S()}, effects=["Adds properties to an existing charge; no material inventory effect."]),
        "cond.chromatography": operation("SpecifyChromatography", "Describe media and eluent of the associated separation without adding another separation.", kind="condition", fields={"stationary_phase": S(), "eluent": S(), "eluent_component": S(), "eluent_carrier": S(), "eluent_percentage": Q("fraction"), "percentage_basis": S(), "associated_separation": R()}, effects=["Qualifies an associated separation; no additional elapsed time or separation."]),
        "cond.thermal": operation("SpecifyThermalCondition", "Qualify an associated action's thermal environment without adding a timed hold or assuming active heating.", kind="condition", fields={"temperature": Q("temperature"), "temperature_condition": S(), "concurrent_action": R()}, effects=["Qualifies an existing interval without adding elapsed time."]),
        "cond.atmosphere": operation("SpecifyAtmosphere", "Qualify a concurrent action's environment or gas contact without performing a second purge.", kind="condition", fields={"atmosphere": S(), "gas": S(), "contact_method": S(), "purge_event": R(), "concurrent_action": R()}, effects=["Qualifies the associated action without inferring establishment or extra duration."]),
        "prov.procedure": operation("ReferenceProcedure", "Preserve reliance on a referenced procedure without expanding unavailable instructions.", kind="provenance", fields={"procedure": S(), "procedure_details": S()}, effects=["Adds provenance only; no unavailable physical operations are invented."]),
    }
    for operation_id in ("op.chromatograph", "cond.chromatography", "op.wash", "op.evaporate"):
        definitions[operation_id]["parameters"]["results"] = O()
    for operation_id in ("op.add", "op.transfer"):
        definitions[operation_id]["parameters"]["amounts"] = O()

    def semantic(value):
        if isinstance(value, dict):
            return {k: semantic(v) for k, v in value.items() if k not in {"name", "description"}}
        if isinstance(value, list):
            return [semantic(v) for v in value]
        return value

    for stable_id, definition in definitions.items():
        # Identity and contract meaning are independent from spelling and aliases.
        body = semantic({k: v for k, v in definition.items() if k not in {"name", "description"}})
        body["id"] = stable_id
        definition["contract_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return definitions


# These groups are curated against the descriptions and state effects in the
# pinned 547-contract registry. Each old name belongs to exactly one group.
GROUPS = {
    "op.add": "AddMassAndMolarAmount AddMaterial AddMaterialWithAmounts AddMeasuredMaterial AddQuantifiedMaterial AddToPlateWells ChargeMaterial ChargeMeasuredMaterial ChargeMeasuredReagent ChargeQuantifiedMaterial ChargeReagent ChargeSubstrate SyringeAddSolutionToPreloadedVial",
    "op.transfer": "DispenseMixture SyringeTransfer TransferSolutionToChargedVessel",
    "op.mix": "MixMaterials StirAtCondition StirAtQualitativeTemperature StirAtTemperature StirAtTemperatureCondition StirMixture StirUnderConditions",
    "op.cool": "Cool CoolMixture CoolToQualitativeTemperature CoolToTemperature",
    "op.heat": "HeatAndStir HeatAtReflux HeatInBath HeatInBlock HeatInBlockWithStirring HeatStirInBlock HeatUnderAtmosphere MicrowaveHeat PreheatApparatus PreheatHeatingBlock PreheatThermalBlock RefluxUnderAtmosphere RampTemperature",
    "op.hold_temperature": "PlaceAndHoldInHeatingBlock",
    "op.atmosphere": "BackfillGas EstablishGasAtmosphere EstablishInertAtmosphere EvacuateAndBackfill FillVesselWithGas FillWithGas",
    "op.degas": "Degas",
    "op.seal": "CapVessel SealVessel",
    "op.filter": "FilterMixture FilterThroughMedium",
    "op.evaporate": "EvaporateSolvent EvaporateToResidue EvaporateUnderPressureCondition EvaporateUnderQualitativePressure EvaporateUnderReducedPressure RemoveSolventUnderPressure RemoveSolventUnderPressureCondition RemoveSolventUnderReducedPressure RemoveSolventUnderVacuum VacuumConcentrate",
    "op.remove_material": "RemoveSolvents",
    "op.dry": "BathDry DryInBath DryInHeatingBath DryOnBath HeatedDry",
    "op.wash": "WashMaterial WashSolid WashWithSolvent",
    "op.dissolve": "Dissolve DissolveInSolvent DissolveMaterials PrepareBinarySolution PrepareSolution",
    "op.suspend": "FormSuspension SuspendInSolvent SuspendMaterials",
    "op.contact": "Preligate",
    "op.adsorb": "AdsorbOnSupport",
    "op.chromatograph": "AttemptChromatographicPurification Chromatograph ChromatographicPurification ChromatographicSeparation FlashChromatography FlashColumnChromatography SilicaGelChromatography",
    "op.purify": "PurifyByReferencedProcedure",
    "op.elute": "ChromatographicElution EluteColumn GradientElution",
    "op.collect": "CollectFractions",
    "op.load": "LoadChromatography",
    "op.recrystallize": "Recrystallize",
    "op.position": "PlaceInHeatedBlock PlaceInHeatingBlock PlaceInPreheatedBlock PlaceInThermalBlock PlaceOnEquipment PlaceVesselInHeatingBath PlaceVesselInHeatingBlock PlaceVesselInThermalBlock PositionVesselOnPlatform",
    "op.configure_vessel": "ConfigureReactionVessel PrepareReactionVessel SelectReactionVessel SetUpReactionVessel SpecifyReactionVessel SpecifyVessel UseDriedVessel UseReactionVessel UseVessel",
    "op.analyze": "AnalyzeByLcms AnalyzeByNmr AnalyzeCrudeNmr AnalyzeMixture AnalyzeNmr AnalyzeReaction AnalyzeReactionMixture AnalyzeSample NmrAnalysis",
    "op.monitor": "MonitorByTimedAnalysis MonitorReaction MonitorReactionProgress",
    "op.aspirate": "MultiAspirate",
    "op.discard": "DiscardMaterial DiscardMixture DiscardReactionMixture DiscardSample",
    "op.stop": "StopReaction",
    "op.measure": "WeighAndChargeMaterial",
    "obs.observation": "AnalyticalObservation InspectMixture ObserveMaterial ObserveMixture ObserveMixtureAppearance RecordObservation RecordReactionObservation",
    "obs.analysis": "ExamineAnalyticalResult ObserveNmr ObserveNmrAnalysis ObserveNmrAssignment RecordAnalyticalObservation RecordCrudeAnalysis RecordCrudeCharacterization RecordCrudeNmrAnalysis RecordNmrAnalysis RecordNmrAssignment RecordNmrObservation RecordNmrResults RecordReactionAnalysis",
    "obs.product": "ObserveIsolatedProduct ObserveProduct ObserveProductProperties ProductCharacterization ProductObservation RecordIsolatedProduct RecordIsolatedProductObservation RecordIsolatedProductProperties RecordIsolationObservation RecordProductAppearance RecordProductObservation RecordProductObservations ReportIsolatedProduct ReportProductObservation",
    "obs.completion": "AssessReactionCompletion ObserveCompletion ObserveConversion ObserveReactionCompletion ObserveReactionProgress RecordCompletionAssessment RecordCompletionObservation RecordConversion RecordConversionObservation RecordReactionCompletion",
    "obs.disposition": "AbandonExperiment AbortReaction DiscontinueExperiment RecordExperimentDisposition RecordWorkupOmission",
    "obs.charge": "RecordChargeDetails RecordChargeMeasurements RecordChargeQuantity",
    "cond.chromatography": "ApplyChromatographyMedia ChromatographyConditions ConfigureChromatographicSeparation ConfigureChromatography RecordChromatographyConditions SetChromatographyConditions SpecifyChromatographyMedia UseChromatographicMedia UseChromatographicMediumAndEluent UseChromatographyMedium",
    "cond.thermal": "MaintainQualitativeTemperature MaintainTemperatureCondition MaintainThermalEnvironment RecordThermalCondition",
    "cond.atmosphere": "BubbleGasContact MaintainChargingEnvironment",
    "prov.procedure": "ProcedureReference ReactByReferencedProcedure RecordProcedureReference ReferenceProcedure",
}


PARAMETER_ALIASES = {
    "molarAmount": "substance_amount", "molar_amount": "substance_amount", "amountOfSubstance": "substance_amount", "amount_of_substance": "substance_amount", "substanceAmount": "substance_amount", "amount_substance": "substance_amount", "amount_mmol": "substance_amount", "reported_substance_amount": "substance_amount",
    "reported_mass": "mass", "reported_volume": "volume", "additional_amount": "additional_amount", "molarLoading": "relative_loading", "molar_loading": "relative_loading", "molar_percentage": "relative_loading",
    "mixing_method": "method", "agitation": "mixing_condition", "stirring": "mixing_condition", "stirring_speed": "rpm", "stirring_rate": "rpm",
    "duration": "duration_s", "elapsedTime": "elapsed_time", "targetTemperature": "temperature", "target_temperature": "temperature", "temperatureScale": "temperature_scale", "temperature_condition": "temperature_condition",
    "heating_apparatus": "apparatus", "heating_device": "apparatus", "heating_method": "method", "heating_mode": "energy_input", "device": "apparatus", "delivery_device": "apparatus", "transfer_device": "apparatus", "delivery_method": "method",
    "closure_type": "closure", "closure_method": "method", "retained_fraction": "keep", "retained_stream": "keep", "medium": "through", "filter_medium": "through",
    "vesselType": "vessel_type", "container_type": "vessel_type", "vesselCapacity": "capacity", "vessel_capacity": "capacity", "handling_environment": "environment", "vessel_annotation": "annotation", "source_annotation": "annotation",
    "stationaryPhase": "stationary_phase", "firstEluent": "first_eluent", "secondEluent": "second_eluent", "firstEluentGrade": "first_eluent_grade", "eluentRatioRange": "eluent_ratio_range", "firstSolvent": "first_eluent", "secondSolvent": "second_eluent", "firstSolventSpecification": "first_eluent_grade", "first_solvent": "first_eluent", "second_solvent": "second_eluent", "first_solvent_grade": "first_eluent_grade", "eluentRatio": "eluent_ratio", "solvent_ratio": "eluent_ratio", "ratio_basis": "percentage_basis", "component_percentage": "eluent_percentage", "eluent_component_percentage": "eluent_percentage", "modifier_percentage": "eluent_percentage", "modifier": "eluent_component", "carrier": "eluent_carrier", "carrier_solvent": "eluent_carrier", "eluent_percentage_basis": "percentage_basis", "associated_separation": "associated_separation", "applies_to": "concurrent_action", "concurrent_condition": "concurrent_action",
    "technique": "method", "analytical_method": "method", "internalStandard": "internal_standard", "internalStandardAmount": "internal_standard_amount", "observedRatio": "observed_ratio", "observedYield": "yield", "observed_yield": "yield", "reportedYield": "yield", "reported_yield": "yield", "yield_percentage": "yield", "isolatedYield": "yield", "isolated_yield": "yield", "product_yield": "yield", "reported_product_mass": "mass", "isolated_mass": "mass", "reported_product": "product", "reported_appearance": "appearance", "physical_form": "appearance",
    "observedTransformation": "transformation", "regioisomerRatio": "regioisomer_ratio", "regioisomerOrder": "ratio_assignment", "ratioAssignments": "ratio_assignment", "ratio_assignment": "ratio_assignment", "regioisomer_ratio": "regioisomer_ratio", "overallSelectivity": "selectivity", "reportedSelectivity": "selectivity",
    "reported_observation": "observation", "reported_assessment": "assessment", "reported_result": "observation", "reported_disposition": "disposition", "physical_termination": "termination_method", "shutdown_method": "termination_method", "disposal_method": "method", "termination_method": "termination_method",
    "procedureReference": "procedure", "procedure_reference": "procedure", "referencedProcedure": "procedure", "referenced_procedure": "procedure", "reference": "procedure", "procedureDetails": "procedure_details", "procedure_reference": "procedure",
    "amounts": "amounts", "solvent_volume_reported": "solvent_volume_literal", "solvent_volume_literal": "solvent_volume_literal", "transfer_amount": "amount", "transferred_quantity": "amount", "destination": "to_vessel", "source_location": "from_vessel", "repetition_qualifier": "repetition_qualifier",
}


def name_index():
    result = {}
    for operation_id, names in GROUPS.items():
        for name in names.split():
            if name in result:
                raise ValueError(f"Duplicate explicit migration: {name}")
            result[name] = operation_id
    return result


def member(key, operation_id, mapping, defaults=None, **extra):
    return {"key": key, "operation_id": operation_id, "parameter_map": mapping, "defaults": defaults or {}, **extra}


def parameter_target(operation_id, source, definition):
    """Move known facts to typed semantic slots; retain their evidence leaves."""
    target = PARAMETER_ALIASES.get(source, source)
    if target in definition["parameters"]:
        return target
    configuration = {"vessel_type", "capacity", "vessel_description", "environment", "location", "charging_context", "initial_solvent_constraint", "condition"}
    if target in configuration:
        return "configuration." + target
    if source.startswith("preloaded_material_"):
        suffix = source.removeprefix("preloaded_material_")
        for word, ordinal in (("one", "1"), ("two", "2"), ("three", "3")):
            if suffix.startswith(word):
                suffix = ordinal + suffix[len(word):]
        ordinal, _, property_name = suffix.partition("_")
        return "initial_contents.material_" + ordinal + "." + {"": "identity", "amount": "substance_amount"}.get(property_name, property_name)
    for prefix, ordinal in (("first_solute", "1"), ("second_solute", "2"), ("solute_one", "1"), ("solute_two", "2"), ("solute_1", "1"), ("solute_2", "2")):
        if source == prefix or source.startswith(prefix + "_"):
            property_name = source[len(prefix):].lstrip("_")
            return "components.solute_" + ordinal + "." + {"": "identity", "amount": "substance_amount"}.get(property_name, property_name)
    specific = {
        "op.add": {"additional_amount": "amounts.additional", "addition_volume": "volume", "addition_duration": "duration_s", "material": "reagent", "destination_plate": "distribution.destination_plate", "plate_well_count": "distribution.plate_capacity", "volume_basis": "distribution.volume_basis", "liquid_handler": "apparatus", "receiving_vessel": "configuration.receiving_vessel", "atmosphere": "conditions.atmosphere", "solution_solvent": "components.solvent", "solvent": "components.solvent", "solvent_volume_literal": "components.solvent_volume_literal", "material_condition": "configuration.material_condition"},
        "op.transfer": {"solution": "material", "volume": "amounts.volume"},
        "op.mix": {"mixing_condition": "conditions.agitation", "temperature_scale": "conditions.temperature_scale"},
        "op.position": {"block_material": "configuration.block_material", "concurrent_agitation": "conditions.agitation", "mixing_condition": "conditions.agitation", "concurrent_action": "source_context.concurrent_action"},
        "op.heat": {"bath": "configuration.bath", "material": "configuration.material", "material_state": "configuration.material_state", "atmosphere_condition": "conditions.atmosphere", "atmosphere_establishment_method": "conditions.atmosphere_establishment_method", "gas_identity": "conditions.gas", "reported_duration": "source_context.reported_duration", "conditioning": "source_context.conditioning", "direction": "ramp.direction", "ramp_character": "ramp.character", "endpoint_qualifier": "ramp.endpoint_qualifier", "endpoint_temperature": "temperature", "concurrent_action": "source_context.concurrent_action", "rpm": "conditions.rpm"},
        "op.atmosphere": {"atmosphere": "conditions.atmosphere", "establishment_method": "method"},
        "op.dissolve": {"solvent_volume_literal": "solvent_volume_literal"},
        "op.suspend": {"materials": "material", "suspension_method": "method", "through": "medium"},
        "op.remove_material": {"material_removed": "material"},
        "op.evaporate": {"material": "material_removed", "removedMaterial": "material_removed", "pressureCondition": "pressure_condition", "reported_residue_description": "results.residue_description", "reported_residue_mass": "results.residue_mass"},
        "op.discard": {"to_vessel": "destination"},
        "op.collect": {"to_vessel": "destination"},
        "op.wash": {"solid": "material", "solvent_volume": "amount", "target": "material", "mass": "results.mass", "reported_product_description": "results.description"},
        "op.dry": {"heating_medium": "bath"},
        "op.measure": {"reagent": "material", "alias": "source_context.material_alias", "handling": "source_context.handling"},
        "op.contact": {"container": "vessel"},
        "op.purify": {"procedure": "procedure_reference", "material": "configuration.material"},
        "op.monitor": {"samplingMethod": "sampling_protocol", "sampling_method": "sampling_protocol", "sampling_schedule": "reported_times", "frequency": "source_context.frequency", "monitoringFrequency": "source_context.frequency", "elapsed_time": "source_context.elapsed_time", "observedConversion": "results.conversion", "observation": "results.observation"},
        "cond.thermal": {"concurrentAction": "concurrent_action"},
        "cond.chromatography": {"concurrent_action": "associated_separation"},
        "cond.atmosphere": {"gas_identity": "gas", "establishment_method": "source_context.establishment_method", "charge_form": "source_context.charge_form", "duration_qualifier": "source_context.duration_qualifier"},
        "obs.charge": {"material": "reagent"},
        "obs.disposition": {"continuation_status": "source_context.continuation_status", "termination_statement": "statement"},
    }
    if source in specific.get(operation_id, {}):
        return specific[operation_id][source]
    if target in specific.get(operation_id, {}):
        return specific[operation_id][target]
    if target == "procedure":
        return "source_context.procedure"
    if operation_id in {"obs.analysis", "obs.product", "obs.completion", "obs.observation", "op.analyze", "op.chromatograph", "cond.chromatography"}:
        # Reported analytical/product outcomes qualify an action; they never
        # become instructions to obtain that outcome or add an internal standard.
        analytical = {"observation", "observations", "analysis", "observed_ratio", "observed_transformation", "ratio_assignment", "regioisomer_ratio", "ratio_identity", "ratio", "selectivity", "transformation", "yield", "yield_percent", "conversion", "product", "mass", "substance_amount", "amount", "appearance", "composition", "composition_method", "spectral_observation", "melting_point_range", "ratio_method", "ratio_measurement", "selectivity_method", "regioisomer_order", "sample", "impurity", "byproducts", "first_byproduct", "first_byproduct_yield", "second_byproduct", "second_byproduct_yield", "component_labels", "component_ratio", "standard", "standard_role", "reported_endpoint", "condition", "timing", "isomer_ratio", "assigned_isomer", "assigned_data", "assignment_method", "characterizationBasis", "yieldReporting", "characterizationMethod", "isolatedMass", "isomerQualifier", "meltingPointRange", "reportedResult", "observedProcess", "reportedIsolationOutcome", "reported_ratio", "reportedAppearance", "reportedProduct", "reportedProductMass", "reported_product_state", "reported_product_appearance", "reported_product_ratio", "reported_product_ratio_assignment", "reported_product_ratio_method", "feasibilityObservation", "materialObservation", "productCount", "productClass"}
        if source in analytical or target in analytical:
            return "results." + target
    if operation_id in {"op.chromatograph", "op.elute", "cond.chromatography"}:
        chromatographic = {"carrier_solvent_designation", "carrier_solvent_grade", "eluent_component_one", "eluent_component_two", "eluent_quantity", "first_eluent_qualifier", "stationary_phase_mass", "column_method", "eluent_carrier", "eluent_component", "eluent_percentage", "percentage_basis", "ratioBasis", "elutionMode", "gradientRange", "gradientVolume"}
        if source in chromatographic or target in chromatographic:
            return "configuration." + target
    if operation_id == "prov.procedure":
        return "source_context." + target
    return target


def migration(definition, definitions, index):
    name = definition["name"]
    operation_id = index[name]
    parameters = definition.get("parameters", {})
    mapping = {source: parameter_target(operation_id, source, definitions[operation_id]) for source in parameters}
    result = {"legacy_name": name, "classification": "parameter_variant", "operation_id": operation_id,
              "parameter_map": mapping, "defaults": {}}
    kind = definitions[operation_id]["kind"]
    if kind in {"observation", "condition", "provenance"}:
        result["classification"] = "observation"
    elif name == definitions[operation_id]["name"]:
        result["classification"] = "synonym"
    elif name in {"Degas", "AdsorbOnSupport", "Recrystallize", "Preligate", "MultiAspirate", "CollectFractions", "LoadChromatography", "StopReaction", "RemoveSolvents"}:
        result["classification"] = "independent"

    if name.startswith("Stir"):
        result["defaults"]["method"] = "stir"
    if name == "MicrowaveHeat":
        result["defaults"]["energy_input"] = "microwave"
    if name in {"HeatAtReflux", "RefluxUnderAtmosphere"}:
        result["defaults"]["mode"] = "reflux"
    if name.startswith("Preheat"):
        result["defaults"]["temperature_subject"] = "apparatus"
        for source in ("apparatus", "block", "thermal_block", "heating_block"):
            if source in mapping:
                mapping[source] = "apparatus"
    if operation_id == "op.dry":
        result["defaults"]["method"] = "thermal"
    if name == "VacuumConcentrate":
        result["defaults"]["endpoint"] = "concentrate"
    if name in {"FlashChromatography", "FlashColumnChromatography"}:
        result["defaults"]["method"] = "flash"
    if name == "SilicaGelChromatography":
        result["defaults"]["stationary_phase"] = "silica gel"
    if name == "AttemptChromatographicPurification":
        result["defaults"]["status"] = "attempted"
    if name == "Preligate":
        result["defaults"]["purpose"] = "preligation"
    if operation_id == "op.atmosphere":
        result["defaults"]["mode"] = {"BackfillGas": "backfill", "FillVesselWithGas": "fill", "FillWithGas": "fill", "EstablishGasAtmosphere": "establish_unspecified", "EstablishInertAtmosphere": "establish_unspecified", "EvacuateAndBackfill": "backfill"}[name]
    if name == "MultiAspirate":
        result["defaults"]["combination"] = "reported_combination"

    if operation_id == "op.position":
        for source in ("block", "heating_block", "platform", "equipment", "bath_type"):
            if source in mapping:
                mapping[source] = "target_equipment"
        for source in ("block_temperature", "blockTemperature", "temperature", "temp_C", "bath_temperature"):
            if source in mapping:
                mapping[source] = "target_temperature"
        for source in ("block_condition", "block_state", "thermal_state", "thermal_preparation", "initial_block_condition", "block_preconditioning", "preconditioning"):
            if source in mapping:
                mapping[source] = "target_condition"

    if operation_id in {"cond.thermal", "cond.chromatography", "cond.atmosphere", "obs.charge"}:
        result["attachment"] = {"kind": {"cond.thermal": "conditions", "cond.chromatography": "chromatography", "cond.atmosphere": "conditions", "obs.charge": "quantities"}[operation_id], "target": "associated_action", "requires_evidence_link": True, "physical_effect": "none"}

    # Compositions are contract-specific. They do not fabricate unreported
    # actions from a broad goal (e.g. recrystallization or preparing a solution).
    if name in {"HeatAndStir", "HeatInBlock", "HeatInBlockWithStirring", "HeatStirInBlock"}:
        steps = []
        if name != "HeatAndStir":
            position_map = {k: ("target_equipment" if k in {"block", "heating_device", "block_material"} else "target_temperature" if k in {"temp_C", "temperature"} else "target_condition") for k in parameters if k in {"block", "heating_device", "block_material", "temp_C", "temperature", "block_condition", "device_condition"}}
            steps.append(member("placement", "op.position", position_map))
        heat_map = {k: v for k, v in mapping.items() if k not in {"agitation", "stirring", "stirring_speed", "stirring_rate", "concurrent_agitation", "concurrent_condition"}}
        mix_map = {k: v for k, v in mapping.items() if k in {"duration", "duration_s", "stirring_speed", "stirring_rate"}}
        steps += [member("heat", "op.heat", heat_map, {"temperature_subject": "apparatus"} if name != "HeatAndStir" else {}), member("mix", "op.mix", mix_map, {"method": "stir"})]
        relations = [{"from": "heat", "to": "mix", "relation": "same_interval"}]
        if name != "HeatAndStir":
            relations.insert(0, {"from": "placement", "to": "heat", "relation": "before"})
        result["composition"] = {"steps": steps, "relations": relations, "time_accounting": "Count shared heating/mixing duration once."}
    elif name in {"PlaceAndHoldInHeatingBlock", "PlaceInHeatedBlock"} and any(k in parameters for k in ("duration", "duration_s")):
        position_map = {k: ("target_equipment" if k in {"block", "heating_block"} else "target_temperature" if k in {"block_temperature", "blockTemperature", "temperature", "temp_C"} else "target_condition") for k in parameters if k not in {"duration", "duration_s"}}
        hold_map = {k: ("duration_s" if k in {"duration", "duration_s"} else "temperature" if k in {"block_temperature", "blockTemperature", "temperature", "temp_C"} else "target_equipment" if k in {"block", "heating_block"} else "thermal_condition") for k in parameters}
        result["composition"] = {"steps": [member("placement", "op.position", position_map), member("hold", "op.hold_temperature", hold_map, {"temperature_subject": "apparatus"})], "relations": [{"from": "placement", "to": "hold", "relation": "before"}], "time_accounting": "Only the hold carries elapsed duration."}
    elif name == "EvacuateAndBackfill":
        result["composition"] = {"steps": [member("evacuate", "op.evacuate", {}), member("backfill", "op.atmosphere", mapping, {"mode": "backfill"})], "relations": [{"from": "evacuate", "to": "backfill", "relation": "before"}], "time_accounting": "No duration or cycle count is inferred."}
    elif name == "WeighAndChargeMaterial":
        result["composition"] = {"steps": [member("weigh", "op.measure", {k: v for k, v in mapping.items() if k in {"reagent", "mass", "volume", "substance_amount"}}, {"method": "weigh"}), member("add", "op.add", mapping)], "relations": [{"from": "weigh", "to": "add", "relation": "before"}], "time_accounting": "Measurements describe the same added portion."}
    elif name in {"DissolveInSolvent", "SuspendInSolvent"}:
        next_operation = "op.dissolve" if name == "DissolveInSolvent" else "op.suspend"
        result["composition"] = {"steps": [member("add_solvent", "op.add", {"reagent": "reagent", "alias": "alias", "volume": "volume"}), member("form", next_operation, {"reagent": "solvent" if next_operation == "op.dissolve" else "medium"})], "relations": [{"from": "add_solvent", "to": "form", "relation": "before"}], "time_accounting": "No mixing mechanism or duration is inferred."}
    if "composition" in result:
        result["classification"] = "composition"
        result["operation_id"] = result["composition"]["steps"][0]["operation_id"]
    return result


def aliases():
    result = []
    def add(identifier, expressions, operation_id, defaults=None, **extra):
        result.append({"id": identifier, "expressions": expressions, "operation_id": operation_id, "classification": "synonym", "parameter_map": {}, "defaults": defaults or {}, **extra})
    add("alias.add", ["Add", "add", "charge", "加入", "投料"], "op.add")
    add("alias.mix.stir", ["Stir", "stir", "搅拌"], "op.mix", {"method": "stir"})
    add("alias.mix.shake", ["shake", "振荡"], "op.mix", {"method": "shake"}, context={"object_role": "material_or_contents", "ambiguous_without_context": True})
    add("alias.mix.vortex", ["vortex", "涡旋混合"], "op.mix", {"method": "vortex"}, context={"object_role": "material_or_contents", "ambiguous_without_context": True})
    add("alias.mix.unspecified", ["Mix", "mix", "混合"], "op.mix", context={"object_role": "material_or_contents", "ambiguous_without_context": True})
    add("alias.heat", ["Heat", "heat", "warm", "加热"], "op.heat")
    add("alias.cool", ["Cool", "cool", "冷却"], "op.cool")
    add("alias.transfer", ["Transfer", "transfer", "转移"], "op.transfer")
    add("alias.wait", ["Wait", "wait", "等待"], "op.wait")
    add("alias.legacy.heat_chill", ["HeatChill"], "op.temperature")
    add("alias.legacy.atmosphere", ["Atmosphere"], "op.atmosphere")
    add("alias.legacy.separate", ["Separate"], "op.separate")
    add("alias.legacy.purify", ["Purify"], "op.purify")
    add("alias.legacy.irradiate", ["Irradiate"], "op.irradiate")
    add("alias.filter", ["Filter", "filter", "过滤"], "op.filter")
    add("alias.evaporate", ["Evaporate", "evaporate", "蒸发"], "op.evaporate")
    add("alias.heat_and_stir", ["heat and stir", "heat while stirring", "加热并搅拌", "边加热边搅拌"], "op.heat", classification="composition", composition={"steps": [member("heat", "op.heat", {"temp_C": "temp_C", "temperature": "temperature", "duration_s": "duration_s"}), member("mix", "op.mix", {"rpm": "rpm", "duration_s": "duration_s"}, {"method": "stir"})], "relations": [{"from": "heat", "to": "mix", "relation": "same_interval"}], "time_accounting": "Count shared duration once."})
    return result


def build(registry_path, output):
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    definitions = operations()
    index = name_index()
    legacy = registry.get("source_operation_contracts", registry.get("extension_operations"))
    if not isinstance(legacy, dict):
        raise ValueError("Registry must contain extension_operations or source_operation_contracts")
    actual = {d["name"] for d in legacy.values()}
    if actual != set(index):
        raise ValueError(f"Explicit semantic classifications differ: missing={sorted(actual-set(index))}, extra={sorted(set(index)-actual)}")
    contracts = {key: migration(value, definitions, index) for key, value in sorted(legacy.items())}
    migrations = {}
    for name in sorted(actual):
        variants = [value for value in contracts.values() if value["legacy_name"] == name]
        reference = dict(variants[0])
        reference["parameter_map"] = dict(sorted({k: v for item in variants for k, v in item["parameter_map"].items()}.items()))
        reference["contract_hashes"] = [key for key, value in contracts.items() if value["legacy_name"] == name]
        reference["requires_exact_contract"] = len({json.dumps({k: v for k, v in item.items() if k not in {"legacy_name", "parameter_map"}}, sort_keys=True) for item in variants}) > 1
        migrations[name] = reference
    atomic = {"schema": "mosaic.atomic-operations/1", "identity_policy": "Stable IDs identify semantics. Display names and aliases are excluded from contract hashes.",
              "missing_parameter_policy": "Explicit not_reported/qualitative/ambiguous markers are values; normalization never guesses them.",
              "evolution_policy": "Known exact mappings normalize deterministically. Unresolved meanings stay unresolved; evidence-backed new semantics enter evolution. Reuse and lossless parameterization precede new IDs.",
              "operations": definitions}
    mapping_document = {"schema": "mosaic.operation-mappings/1", "matching_policy": "Exact expressions or exact pinned legacy contracts only. No edit distance, name similarity or model-decided runtime merging.",
                        "negative_policy": "Normalize labels and parameter names only; do not repair invalid references, absent equipment, missing quantities or deliberately wrong values.",
                        "composition_policy": "Explicit source actions only. same_interval members overlap and count elapsed time once. Qualifiers and observations never create extra actions.",
                        "source_registry": str(registry_path.relative_to(ROOT)).replace("\\", "/") if registry_path.is_relative_to(ROOT) else registry_path.name,
                        "source_registry_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
                        "aliases": aliases(), "migrations": migrations, "contracts": contracts}
    output.mkdir(parents=True, exist_ok=True)
    for name, body in (("atomic_operations.yaml", atomic), ("operation_mappings.yaml", mapping_document)):
        # Aliases and each exact legacy migration stay in the mapping file; no
        # alias addition changes a canonical operation's semantic contract hash.
        (output / name).write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8", newline="\n")
    print(json.dumps({"canonical_entries": len(definitions), "legacy_names": len(migrations), "legacy_contracts": len(contracts)}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path, nargs="?")
    parser.add_argument("--registry", dest="registry_option", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "libraries")
    args = parser.parse_args()
    source = args.registry_option or args.registry
    if source is None:
        parser.error("a frozen registry path is required")
    build(source.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
