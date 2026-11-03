/** Deterministic 10x10 project payload for API-driven browser tests. */
export function projectPayload(name) {
  const shell = {
    type: "delta",
    constellation_property: {
      identifier: "LEO",
      amount_of_orbit_plane: 10,
      amount_of_satellite_per_orbit_plane: 10,
      inclination: 70,
      phase_difference_between_satellites: true,
      mean_revolution_per_day: 14.4,
    },
    orbital_connectivity_property: {
      adjacent_inter_satellite_shifting: 0,
      maximum_inter_satellite_count: 4,
      maximum_inter_satellite_range_distance: 1500.0,
      maximum_ground_station_range: 1200.0,
      maximum_user_terminal_range: 1000.0,
      maximum_connected_ground_object: 10000,
      maximum_connected_user_terminal: 500,
      maximum_connected_ground_station: 10,
    },
    ground_object_white_list: ["Ground Stations"],
  };
  const ground = {
    identifier: "Ground Stations",
    stations: [
      {
        index: 0,
        name: "Berlin",
        latitude: 52.52,
        longitude: 13.405,
        elevation_km: 0.034,
      },
    ],
    type: "ground_station",
    connectivity_properties: {
      ground_to_space_connections_strategy: "everything-visible",
      elevation_above_horizon: 10,
      maximum_satellite_range_distance: 1500.0,
      shell_white_lists: ["LEO"],
      maximum_connected_satellites: 3,
    },
  };
  return {
    name,
    update_time: 5,
    start_date: "01/01/2024 00:00:00",
    end_date: "01/01/2024 00:10:00",
    isl_capacity: 100000,
    gs_capacity: 100000,
    save_path: "",
    walker_shells_json: JSON.stringify([shell]),
    ground_objects_properties_json: JSON.stringify([ground]),
  };
}
