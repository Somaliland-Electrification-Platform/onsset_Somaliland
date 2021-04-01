# Defines the modules

import logging
import os

import pandas as pd
from onsset import (SET_ELEC_ORDER, SET_LCOE_GRID, SET_MIN_GRID_DIST, SET_GRID_PENALTY,
                    SET_MV_CONNECT_DIST, SET_WINDCF, SettlementProcessor, Technology)

try:
    from onsset.specs import (SPE_COUNTRY, SPE_ELEC, SPE_ELEC_MODELLED,
                              SPE_ELEC_RURAL, SPE_ELEC_URBAN, SPE_END_YEAR,
                              SPE_GRID_CAPACITY_INVESTMENT, SPE_GRID_LOSSES,
                              SPE_MAX_GRID_EXTENSION_DIST,
                              SPE_NUM_PEOPLE_PER_HH_RURAL,
                              SPE_NUM_PEOPLE_PER_HH_URBAN, SPE_POP, SPE_POP_FUTURE,
                              SPE_START_YEAR, SPE_URBAN, SPE_URBAN_FUTURE,
                              SPE_URBAN_MODELLED)
except ImportError:
    from specs import (SPE_COUNTRY, SPE_ELEC, SPE_ELEC_MODELLED,
                       SPE_ELEC_RURAL, SPE_ELEC_URBAN, SPE_END_YEAR,
                       SPE_GRID_CAPACITY_INVESTMENT, SPE_GRID_LOSSES,
                       SPE_MAX_GRID_EXTENSION_DIST,
                       SPE_NUM_PEOPLE_PER_HH_RURAL,
                       SPE_NUM_PEOPLE_PER_HH_URBAN, SPE_POP, SPE_POP_FUTURE,
                       SPE_START_YEAR, SPE_URBAN, SPE_URBAN_FUTURE,
                       SPE_URBAN_MODELLED)
from openpyxl import load_workbook

# logging.basicConfig(format='%(asctime)s\t\t%(message)s', level=logging.DEBUG)


def calibration(specs_path, csv_path, specs_path_calib, calibrated_csv_path):
    """

    Arguments
    ---------
    specs_path
    csv_path
    specs_path_calib
    calibrated_csv_path
    """
    specs_data = pd.read_excel(specs_path, sheet_name='SpecsData')
    settlements_in_csv = csv_path
    settlements_out_csv = calibrated_csv_path

    onsseter = SettlementProcessor(settlements_in_csv)

    num_people_per_hh_rural = float(specs_data.iloc[0][SPE_NUM_PEOPLE_PER_HH_RURAL])
    num_people_per_hh_urban = float(specs_data.iloc[0][SPE_NUM_PEOPLE_PER_HH_URBAN])

    onsseter.condition_df()
    onsseter.df[SET_GRID_PENALTY] = onsseter.grid_penalties(onsseter.df)
    onsseter.df[SET_WINDCF] = onsseter.calc_wind_cfs()

    pop_actual = specs_data.loc[0, SPE_POP]
    start_year = int(specs_data.loc[0, SPE_START_YEAR])
    end_year = int(specs_data.loc[0, SPE_END_YEAR])
    intermediate_year = int(specs_data.loc[0, 'IntermediateYear'])

    major_urban_centers_pop = 10000  # Minimum population threshold

    # Other urban areas threshold (all settlements with a population above the threshold and
    # within the maxiumum distance from main roads are considered as urban areas)
    other_urban_areas_pop = 1500  # Minimum population threshold
    other_urban_areas_road_dist = 5  # Max road distance thershold (km)
    urban_pop_growth_rate = 0.029  ### Write the annual population growth rate expected in urban areas (e.g. 0.029 for 2.9%)
    rural_pop_growth_rate = 0.029  ### Write the annual population growth rate expected in rural areas (e.g. 0.029 for 2.9%)

    pop_modelled, urban_modelled = \
        onsseter.calibrate_current_pop_and_urban(pop_actual, major_urban_centers_pop, other_urban_areas_pop,
                                                 other_urban_areas_road_dist, num_people_per_hh_rural,
                                                 num_people_per_hh_urban)

    onsseter.project_pop_and_urban(urban_pop_growth_rate, rural_pop_growth_rate,
                                   start_year, end_year, intermediate_year)

    mini_grid_electification_ratio = 0.67  # Share of households in areas with existing mini-grids considered to be electrified

    elec_modelled, rural_elec_ratio, urban_elec_ratio = onsseter.mini_grid_electrified(mini_grid_electification_ratio, start_year)

    specs_data.loc[0, SPE_URBAN_MODELLED] = urban_modelled
    specs_data.loc[0, SPE_ELEC_MODELLED] = elec_modelled
    specs_data.loc[0, 'rural_elec_ratio_modelled'] = rural_elec_ratio
    specs_data.loc[0, 'urban_elec_ratio_modelled'] = urban_elec_ratio

    book = load_workbook(specs_path)
    writer = pd.ExcelWriter(specs_path_calib, engine='openpyxl')
    writer.book = book
    # RUN_PARAM: Here the calibrated "specs" data are copied to a new tab called "SpecsDataCalib". 
    # This is what will later on be used to feed the model
    specs_data.to_excel(writer, sheet_name='SpecsDataCalib', index=False)
    writer.save()
    writer.close()

    #logging.info('Calibration finished. Results are transferred to the csv file')
    onsseter.df.to_csv(settlements_out_csv, index=False)


def scenario(specs_path, calibrated_csv_path, results_folder, summary_folder):
    """

    Arguments
    ---------
    specs_path : str
    calibrated_csv_path : str
    results_folder : str
    summary_folder : str

    """

    scenario_info = pd.read_excel(specs_path, sheet_name='ScenarioInfo')
    scenarios = scenario_info['Scenario']
    scenario_parameters = pd.read_excel(specs_path, sheet_name='ScenarioParameters')
    specs_data = pd.read_excel(specs_path, sheet_name='SpecsDataCalib')
    print(specs_data.loc[0, SPE_COUNTRY])

    for scenario in scenarios:
        print('Scenario: ' + str(scenario + 1))
        country_id = specs_data.iloc[0]['CountryCode']

        tier_index = scenario_info.iloc[scenario]['Target_electricity_consumption_level']
        pv_index = scenario_info.iloc[scenario]['PV_cost_adjust']
        diesel_index = scenario_info.iloc[scenario]['Diesel_price']
        grid_index = scenario_info.iloc[scenario]['Grid_option']
        intensification_index = scenario_info.iloc[scenario]['Intensification']
        dist_costs = scenario_info.iloc[scenario]['Distribution_costs']

        prioritization = 5

        five_year_target = scenario_parameters.iloc[0]['5YearTarget']  # Tarrget electrification rate in 2025

        grid_price = scenario_parameters.iloc[grid_index]['GridGenerationCost']  # Generation cost + HV transmission cost (USD/kWh)
        grid_option = scenario_parameters.iloc[grid_index]['GridOption']  # 1 = MG and SA only, 2 = split backbone, 3 = national backbone

        threshold = scenario_parameters.iloc[intensification_index]['Threshold']  # Maximum cost for forced grid extension (USD/household)
        auto_intensification = scenario_parameters.iloc[intensification_index]['AutoIntensificationKM'] # Forced grid extension distance (km)

        rural_demand_low = scenario_parameters.iloc[tier_index]['RuralTargetLow']  # kWh/household/year
        rural_demand_high = scenario_parameters.iloc[tier_index]['RuralTargetHigh']  # kWh/household/year
        rural_commercial_demand_factor = scenario_parameters.iloc[tier_index]['rural_commercial_demand_factor']  # Share of residential demand

        urban_demand_low = scenario_parameters.iloc[tier_index]['UrbanTargetLow']  # kWh/household/year
        urban_demand_high = scenario_parameters.iloc[tier_index]['UrbanTargetHigh']  # kWh/household/year
        urban_commercial_demand_factor = scenario_parameters.iloc[tier_index]['urban_commercial_demand_factor']  # Share of residential demand

        lv_cost = scenario_parameters.iloc[dist_costs]['LVCost']
        mv_cost = scenario_parameters.iloc[dist_costs]['MVCost']

        pv_panel_cost = scenario_parameters.iloc[pv_index]['PV_Cost_adjust']

        diesel_price = scenario_parameters.iloc[diesel_index]['DieselPrice']

        annual_new_grid_connections_limit_2025 = scenario_parameters.iloc[0]['GridConnectionsLimitThousands2025'] * 1000
        annual_new_grid_connections_limit_2030 = scenario_parameters.iloc[0]['GridConnectionsLimitThousands2030'] * 1000


        settlements_in_csv = calibrated_csv_path
        settlements_out_csv = os.path.join(results_folder,
                                           '{}-1-{}_{}_{}_{}_{}_{}.csv'.format(country_id, grid_index, intensification_index,
                                                                            tier_index, dist_costs,
                                                                            pv_index, diesel_index, ))
        summary_csv = os.path.join(summary_folder,
                                   '{}-1-{}_{}_{}_{}_{}_{}_summary.csv'.format(country_id, grid_index, intensification_index,
                                                                            tier_index, dist_costs,
                                                                            pv_index, diesel_index))

        onsseter = SettlementProcessor(settlements_in_csv)

        start_year = specs_data.iloc[0][SPE_START_YEAR]
        end_year = specs_data.iloc[0][SPE_END_YEAR]

        num_people_per_hh_rural = 5.7  # float(specs_data.iloc[0][SPE_NUM_PEOPLE_PER_HH_RURAL])
        num_people_per_hh_urban = 6.6  # float(specs_data.iloc[0][SPE_NUM_PEOPLE_PER_HH_URBAN])
        max_grid_extension_dist = 50  # float(specs_data.iloc[0][SPE_MAX_GRID_EXTENSION_DIST])

        min_mini_grid_pop = 100  # Minimum pop required in settlement for mini-grids to be considered as an option
        discount_rate = 0.10

        # RUN_PARAM: Fill in general and technology specific parameters (e.g. discount rate, losses etc.)
        Technology.set_default_values(base_year=start_year,
                                      start_year=start_year,
                                      end_year=end_year,
                                      discount_rate=discount_rate,
                                      lv_line_cost=lv_cost,
                                      mv_line_cost=mv_cost)

        mg_pv_hybrid_calc = Technology(om_of_td_lines=0.02,
                                       distribution_losses=0.05,
                                       connection_cost_per_hh=20,
                                       capacity_factor=0.5,
                                       tech_life=30,
                                       mini_grid=True,
                                       hybrid=True)

        mg_wind_hybrid_calc = Technology(om_of_td_lines=0.02,
                                         distribution_losses=0.05,
                                         connection_cost_per_hh=20,
                                         capacity_factor=0.5,
                                         tech_life=30,
                                         mini_grid=True,
                                         hybrid=True)

        mg_hydro_calc = Technology(om_of_td_lines=0.02,
                                   distribution_losses=0.05,
                                   connection_cost_per_hh=20,
                                   capacity_factor=0.5,
                                   tech_life=35,
                                   capital_cost={float("inf"): 5000},
                                   om_costs=0.03,
                                   mini_grid=True)

        sa_pv_calc = Technology(base_to_peak_load_ratio=0.8,
                                tech_life=15,
                                om_costs=0.075,
                                capital_cost={float("inf"): 2700,
                                              1: 2700,
                                              0.200: 2700,
                                              0.080: 2625,
                                              0.030: 2200,
                                              0.006: 9200
                                              },
                                standalone=True)

        sa_diesel_cost = {'diesel_price': diesel_price,
                          'efficiency': 0.28,
                          'diesel_truck_consumption': 14,
                          'diesel_truck_volume': 300}

        mg_diesel_cost = {'diesel_price': diesel_price,
                          'efficiency': 0.33,
                          'diesel_truck_consumption': 14,
                          'diesel_truck_volume': 300}

        # RUN_PARAM: One shall define here the years of analysis (excluding start year),
        # together with access targets per interval and timestep duration
        yearsofanalysis = [2025, 2030]
        eleclimits = {2025: five_year_target, 2030: 1}
        time_steps = {2025: 5, 2030: 5}

        elements = ["1.Population", "2.New_Connections", "3.Capacity", "4.Investment"]
        techs = ["Grid", "SA_PV_mobile", "SA_PV", "MG_Diesel", "MG_PV", "MG_Wind", "MG_Hydro", "MG_PV_Hybrid",
                 "MG_Wind_Hybrid"]
        sumtechs = []
        for element in elements:
            for tech in techs:
                sumtechs.append(element + "_" + tech)
        total_rows = len(sumtechs)
        df_summary = pd.DataFrame(columns=yearsofanalysis)
        for row in range(0, total_rows):
            df_summary.loc[sumtechs[row]] = "Nan"

        onsseter.grid_cell_area()

        for year in yearsofanalysis:
            eleclimit = eleclimits[year]
            time_step = time_steps[year]

            if year - time_step == start_year:
                grid_cap_gen_limit = 999999999
                grid_connect_limit = time_step * annual_new_grid_connections_limit_2025
            else:
                grid_cap_gen_limit = 999999999
                grid_connect_limit = time_step * annual_new_grid_connections_limit_2030

            onsseter.set_scenario_variables(year, num_people_per_hh_rural, num_people_per_hh_urban, time_step, start_year,
                                            rural_demand_low, rural_demand_high, urban_demand_low, urban_demand_high,
                                            urban_commercial_demand_factor, rural_commercial_demand_factor)

            onsseter.diesel_cost_columns(sa_diesel_cost, mg_diesel_cost, year)

            mg_wind_hybrid_investment, mg_wind_hybrid_capacity = \
                onsseter.calculate_wind_hybrids_lcoe(year, year - time_step, end_year, time_step,
                                                     mg_wind_hybrid_calc, battery_cost=139, wind_cost=2800,
                                                     diesel_cost=150, inverter_cost=142, wind_life=20,
                                                     diesel_life=10, inverter_life=10, discount_rate=discount_rate,
                                                     min_pop=min_mini_grid_pop)

            mg_pv_hybrid_investment, mg_pv_hybrid_capacity = \
                onsseter.calculate_pv_hybrids_lcoe(year, year - time_step, end_year, time_step, mg_pv_hybrid_calc,
                                                   pv_panel_cost, diesel_gen_investment=150,
                                                   discount_rate=discount_rate,
                                                   battery_cost=139, inverter_cost=142, pv_life=25, diesel_life=10,
                                                   inverter_life=10, min_pop=min_mini_grid_pop)

            grid_calc = onsseter.grid_option(grid_option, auto_intensification, year, distribution_om=0.02,
                                             distribution_losses=0.05, grid_losses=0.10,
                                             connection_cost_per_household=20,
                                             grid_power_plants_capital_cost=2000, start_year=start_year,
                                             grid_generation_cost=grid_price,
                                             split_HV_transmission_cost=0,
                                             national_HV_transmission_cost=0)

            if year == 2025:
                onsseter.current_mv_line_dist()

            sa_pv_investment, mg_hydro_investment = onsseter.calculate_off_grid_lcoes(mg_hydro_calc, sa_pv_calc, year,
                                                                                      end_year, time_step,
                                                                                      min_mini_grid_pop)

            grid_investment, grid_cap_gen_limit, grid_connect_limit = \
                onsseter.pre_electrification(grid_price, year, time_step, end_year, grid_calc, grid_cap_gen_limit,
                                             grid_connect_limit)

            onsseter.df[SET_LCOE_GRID + "{}".format(year)], onsseter.df[SET_MIN_GRID_DIST + "{}".format(year)], \
            onsseter.df[SET_ELEC_ORDER + "{}".format(year)], onsseter.df[SET_MV_CONNECT_DIST], grid_investment = \
                onsseter.elec_extension(grid_calc, max_grid_extension_dist, year, start_year, end_year,
                                        time_step, grid_investment, grid_cap_gen_limit, grid_connect_limit,
                                        auto_intensification, prioritization, threshold)

            onsseter.results_columns(year, time_step, prioritization, auto_intensification)

            onsseter.calculate_investments(sa_pv_investment, mg_hydro_investment, mg_pv_hybrid_investment,
                                           mg_wind_hybrid_investment, grid_investment, year, grid_option)

            onsseter.apply_limitations(eleclimit, year, time_step, prioritization, auto_intensification)

            onsseter.calculate_new_capacity(mg_pv_hybrid_capacity, mg_wind_hybrid_capacity, mg_hydro_calc, sa_pv_calc,
                                            grid_calc, year, grid_option)

            onsseter.calc_summaries(df_summary, sumtechs, year, grid_option, auto_intensification)

        for i in range(len(onsseter.df.columns)):
            if onsseter.df.iloc[:, i].dtype == 'float64':
                onsseter.df.iloc[:, i] = pd.to_numeric(onsseter.df.iloc[:, i], downcast='float')
            elif onsseter.df.iloc[:, i].dtype == 'int64':
                onsseter.df.iloc[:, i] = pd.to_numeric(onsseter.df.iloc[:, i], downcast='signed')

        df_summary.to_csv(summary_csv, index=sumtechs)
        onsseter.df.to_csv(settlements_out_csv, index=False)

        # logging.info('Finished')
