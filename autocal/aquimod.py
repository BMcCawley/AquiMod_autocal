import os
from pathlib import Path

import numpy as np
import pandas as pd


class AquiModAWS:
    def __init__(self, model_dir):
        self.model_dir = model_dir
        self.input_path = Path(model_dir, "Input.txt")
        self.observations_path = Path(model_dir, "Observations.txt")
        self._model_data = pd.read_csv("model_data.csv")

    def _edit_line(self, path, line_number: int, text: str):
        """Edit a text file at a certain line. Automatically places newline char."""
        with open(path, "r") as f:
            lines = f.readlines()
            lines[line_number] = text + "\n"
        with open(self.input_path, "w") as f:
            f.writelines(lines)

    def _read_line(self, path, line_number: int) -> str:
        """Read contents of a certain line within a file"""
        with open(path, "r") as f:
            lines = f.readlines()
        return lines[line_number].replace("\n", "")

    def _read_data(self, path, skiprows=None) -> pd.DataFrame:
        """Read AquiMod data in a table format"""
        return pd.read_csv(path, sep="\t", index_col=False, skiprows=skiprows)

    def _delete_dir_contents(self, directory):
        """Delete contents"""
        for path in Path(self.model_dir, directory).glob("*"):
            os.remove(path)

    @property
    def module_config(self) -> dict[str, int]:
        """Get module numbers from input file"""
        line = self._read_line(self.input_path, 1).split(" ")
        return {
            "soil": int(line[0]),
            "unstaurated": int(line[1]),
            "saturated": int(line[2]),
        }

    @module_config.setter
    def module_config(self, config: list[int]):
        """Set module numbers in input file"""
        text = " ".join([str(val) for val in config])
        self._edit_line(self.input_path, 1, text)

    @property
    def simulation_mode(self) -> str:
        """Get the simulation mode from the input file"""
        return self._read_line(self.input_path, 4)

    @simulation_mode.setter
    def simulation_mode(self, mode: str):
        """Set simulation mode in input file"""
        self._edit_line(self.input_path, 4, mode)

    @property
    def number_of_runs(self) -> int:
        """Get number of runs from input file"""
        return self._read_line(self.input_path, 10)

    @number_of_runs.setter
    def number_of_runs(self, num_runs: int):
        """Set number of runs in input file"""
        self._edit_line(self.input_path, 10, str(num_runs))

    @property
    def calibrated_variable(self) -> str:
        """Get calibrated variable from input file"""
        self._read_line(self.input_path, 7)

    @calibrated_variable.setter
    def calibrated_variable(self, variable: str):
        """Set calibrated variable (either 'g' or 's') in input file"""
        self._edit_line(self.input_path, 7, variable)

    @property
    def module_names(self) -> dict[str, str]:
        """Get module names"""
        df_dict = {
            "soil": self._model_data[self._model_data["component"] == "soil"],
            "unsaturated": self._model_data[
                self._model_data["component"] == "unsaturated"
            ],
            "saturated": self._model_data[self._model_data["component"] == "saturated"],
        }
        modules = self.module_config

        return {
            component: df[
                df["module_number"] == modules[component], "module_name"
            ].unique()[0]
            for component, df in df_dict.items()
        }

    @property
    def parameters(self) -> dict[str, list[str]]:
        """Get parameter names as list value for each component key"""
        return {
            module_name: list(
                self._model_data[
                    self._model_data["module_name"] == module_name, "component_name"
                ].unique()
            )
            for module_name in self.module_names.values()
        }

    @property
    def parameter_line_numbers(self) -> dict[str, int]:
        """Get parameter line numbers as a dictionary with parameter as key"""
        return {
            parameter: self._model_data[
                (self._model_data["module_name"] == module)
                & (self._model_data["parameter"] == parameter),
                "line_number",
            ].unique()[0]
            for module, parameter in self.parameters.items()
        }

    @property
    def calibration_paths(self) -> dict[str, Path]:
        """Get paths to calibration files"""
        return {
            component: Path(self.model_dir, "Calibration", module_name + "_calib.txt")
            for component, module_name in self.module_names
        }

    @property
    def evaluation_paths(self) -> dict[str, Path]:
        """Get paths to evaluation files"""
        return {
            component: Path(self.model_dir, "Evaluation", module_name + "_eval.txt")
            for component, module_name in self.module_names
        }

    @property
    def output_calibration_paths(self) -> dict[str, Path]:
        """Get the paths to output calibration files"""
        paths = {
            component: Path(self.model_dir, "Output", module + "_calib.out")
            for component, module in self.module_names.items()
        }
        if self.calibrated_variable == "g":
            paths["fit"] = Path(self.model_dir, "Output", "fit_calib_GWL.out")
        elif self.calibrated_variable == "s":
            paths["fit"] = Path(self.model_dir, "Output", "fit_calib_SM.out")

        return paths

    @property
    def output_evaluation_paths(self) -> dict[str, list[Path]]:
        """Get the paths to output evaluation files"""
        # Could search for paths using path.glob or use the number of runs property
        # Opted for using the number of runs property
        # Also need to consider if some output files have not been saved, as with "write model output files"
        # For now assume that everything is saved
        path_dict = {}
        for component, module in self.module_names.items():
            path_list = [
                Path(self.model_dir, "Output", module + f"_TimeSeries{i}.out")
                for i in range(1, self.number_of_runs + 1)
            ]
            path_dict[component] = path_list

        if self.calibrated_variable == "g":
            path_dict["fit"] = Path(self.model_dir, "Output", "fit_eval_GWL.out")
        elif self.calibrated_variable == "s":
            path_dict["fit"] = Path(self.model_dir, "Output", "fit_eval_SM.out")

    @property
    def calibration_parameters(self) -> dict[str, pd.DataFrame]:
        """
        Get parameter limits as dict of dataframes.
        Dataframes arranged with parameters as columns.
        """
        # Instantiate outer dictionary
        outer = {}
        # Loop through each component and its calibration file path
        for component, path in self.calibration_paths.items():
            # Instantiate inner dictionary
            inner = {}
            # Loop through each parameter in the current component
            for parameter in self.parameters[component]:
                # Get min and max value for each parameter as string
                minmax = self._read_line(path, self._parameter_line_numbers[parameter])
                # Split string into list and cast elements into floats
                minmax_list = [float(val) for val in minmax.split(" ")]
                # Assign list of min and max floats to inner dictionary
                inner[parameter] = minmax_list
            # Convert inner dictionary to DataFrame and assign to outer dictionary
            outer[component] = pd.DataFrame(inner, index=["min", "max"])

        return outer

    @calibration_parameters.setter
    def calibration_parameters(self, calib_dict: dict[str, pd.DataFrame]) -> None:
        """Set calibration parameters"""
        # Don't think I need to work on this one right now
        pass

    @property
    def evaluation_parameters(self) -> dict[str, pd.DataFrame]:
        """Get evaluation parameters as dict of dataframes"""
        return {
            component: self._read_data(path)
            for component, path in self.evaluation_paths.items()
        }

    @evaluation_parameters.setter
    def evaluation_parameters(self, eval_dict: dict[str, pd.DataFrame]) -> None:
        """Set evaluation parameters"""
        for component, df in eval_dict.items():
            df.to_csv(self.evaluation_paths[component], sep="\t", index=False)

    def run(
        self,
        module_config: list[int] = None,
        sim_mode: str = None,
        calib_var: str = None,
        num_runs: int = None,
    ):
        if module_config is not None:
            self.module_config = module_config
        if sim_mode is not None:
            self.simulation_mode = sim_mode
        if calib_var is not None:
            self.calibrated_variable = calib_var
        if num_runs is not None:
            self.number_of_runs = num_runs

        # self._delete_dir_contents(Path(self.model_dir, "Output"))
        os.system(f"AquiModAWS {self.model_dir}")

    def read_performance_output(self) -> dict[str, pd.DataFrame]:
        """
        Read output files from the most recent call of self.run().
        Includes parameter values and model performance.
        """
        # Don't forget that a user can just look at the output files themselves
        # GWLForecaster reads timeseries outputs and creates a csv with a column for
        # each individual model run.
        # GWLForecaster isn't bothered at all with fit as it is just forecast data.
        if self.simulation_mode == "c":
            return {
                component: self._read_data(path)
                for component, path in self.output_calibration_paths.items()
            }
        elif self.simulation_mode == "e":
            output = {
                component: self._read_data(path)
                for component, path in self.evaluation_paths.items()
            }
            output["fit"] = pd.read_csv(
                self.output_evaluation_paths["fit"], sep="\t", index_col=False
            )
            return output

    def read_timeseries_output(self):
        """Read output timeseries files"""
        pass

    def _cce(
        self,
        complx: dict[str, pd.DataFrame],
        simplx_size: int,
        alpha: int,
        reflection_coef=1,
        contraction_coef=0.5,
    ):
        """
        q: number of points in simplex [2 <= q <= m]
        m: number of points in complex
        alpha: user-defined number of evolution iterations per simplex [alpha >= 1]
        beta: [beta >= 1]

        1. Assign weights to each point in the complex
        2. Randomly select weighted simplex points
        3. Reorder simplex by best performing points
        4. Compute the centroid of the simplex
        5. Reflect the worst performing point through the centroid
        6. Check that the new point is within the parameter space/smallest complx hypercube:
            - If true, go to 8
            - If false, go to 7
        7. Generate random point within the parameter space (mutation)
        8. Run AquiMod for new point (either new or new) to get NSE
        9. Check that new point performs better than previous worst point:
            - If true, go to 15
            - If false, go to 10
        10. Contract the worst performing point towards the centroid
        11. Run AquiMod for new point to get NSE
        12. Check that new point performs better than previous worst point:
            - If true, go to 15
            - If false, go to 13
        13. Generate random point within the parameter space (mutation)
        14. Run AquiMod with the new point
        15. Replace worst performing point with new point
        16. Repeat steps 4 - 15 alpha times where alpha >= 1
        """
        # I have just realised that I can't do CCE steps individually on components
        # Because they need to all be done together for control flow purposes
        # I could either break up the for loop  for the control flow checks
        # I could also save the complx keys and df column names as a mapping
        # and then use the mapping to recreate the separate dictionary entries

        # Convert complx from dictionary to a single dataframe
        complx_df = pd.concat(complx.values(), axis=1)

        m = len(complx_df)
        # 1. Calculate triangular distribution
        # Make sure that complx is ordered by ObjectiveFunction
        complx_df = complx_df.sort_by("ObjectiveFunction", ascending=False)
        complx_df["weight"] = (2 * (m + 1 + range(1, m + 1))) / (m * (m + 1))
        # Normalise weights so that their sum == 1
        complx_df["weight"] /= complx["weight"].sum()
        # 2. Select simplx points from weighted complx points
        simplx = complx_df.loc[
            np.random.choice(
                complx_df.index, simplx_size, replace=False, p=complx_df["weight"]
            )
        ]
        for _ in range(alpha):
            # 3. Restore order to simplx
            simplx = simplx.sort_by("ObjectiveFunction", ascending=False)
            # 4. Compute centroid of simplx
            centroid = simplx.mean().to_frame().T
            # Drop weight and ObjectiveFunction value of centroid
            # centroid = centroid.drop(["ObjectiveFunction", "weight"], axis=1)
            # 5. Perform reflection step of the worst performing point through centroid
            worst = simplx.iloc[-1]
            worst = worst.reset_index(drop=True)
            new = centroid + reflection_coef * (centroid - worst)
            new = new.reset_index(drop=True)  # is this necessary? yes
            # 6. Check that the new point is still within parameter space
            # Get parameter bounds
            parameter_lims = pd.concat(self.calibration_parameters.values())
            within_parameter_space = True
            for col in new.columns:
                minimum = parameter_lims.loc["min", col]
                maximum = parameter_lims.loc["max", col]
                if not minimum <= new.loc[0, col] <= maximum:
                    within_parameter_space = False
            # 7. If new point is outside parameter space, perform mutation instead
            if not within_parameter_space:
                # Mutation performed nut labelled as reflection
                # Current parameter calibration limits define parameter space
                # Although not the smallest possible complx hypercube
                # Can try and implement this version later
                self.run(sim_mode="c", num_runs=1)
            # 8.
            else:
                # Run AquiMod using the new point
                # AquiMod must be run in evaluation mode for this
                # Evaluation files need to be written for each module
                # Need to separate new into components
                eval_params = {
                    component: new[df.cols] for component, df in complx.items()
                }

                self.evaluation_parameters = eval_params
                self.run(sim_mode="e", num_runs=1)

            new = pd.concat(self.read_performance_output().values(), axis=1)
            # 9. Check if new point performs worse than worst point
            if new.loc[0, "ObjectiveFunction"] < worst[0, "ObjectiveFunction"]:
                # 10. Contract the worst performing point towards the centroid
                new = worst + contraction_coef * (centroid - worst)
                eval_params = {
                    component: new[df.cols] for component, df in complx.items()
                }
                self.evaluation_parameters = eval_params
                # 11. Run AquiMod for new point
                self.run(sim_mode="e", num_runs=1)
                new = pd.concat(self.read_performance_output().values(), axis=1)
            # 12. Check if new point performs worse than the worst point
            if new.loc[0, "ObjectiveFunction"] < worst[0, "ObjectiveFunction"]:
                # 13. Generate random point within parameter space
                # 14. Run AquiMod for new point
                self.run(sim_mode="c", num_runs=1)
                new = pd.concat(self.read_performance_output().values(), axis=1)
            # 15. Replace worst performing point with new point in simplx
            simplx.iloc[-1] = new

        complx_df.loc[simplx.index] = simplx

    def calibrate(
        self, num_complexes: int, complex_size: int, simplex_size: int, alpha: int
    ) -> dict[str, pd.DataFrame]:
        """
        Calibrate model according to the shuffled complex evolution algorithm.

        n: number of dimensions (parameters/degrees of freedom) to calibrate
        p: number of complexes [p >= 1]
        m: number of points in each complex [m >= n+1]
        q: number of points in simplex [2 <= q <= m]

        sample_size: initial sample size [s = p * m]

        1. Run AquiMod for s random points in the parameter space.
        2. Sort s points in order from best objective function value.
        3. Partition points into p complexes of m points.
            - Points partitioned in repeating order [1:a, 2:b, 3:c, 4:a, 5:b, 6:c]
        4. Evolve each complex according to CCE algorithm.
        5. Shuffle complexes.
            - Combine points in evolved complexes back into a single population
            - Sort the population in rank order
            - Repartition into complexes as before
        6. Check for convergence criteria
            - Stop if maximum number of trials reached
            - Stop if objective function value not significantly increased
        7. Return to step 3/4.
        """
        # Total sample points
        sample_size = num_complexes * complex_size
        # 1. Run AquiMod for all points
        self.run(sim_mode="c", num_runs=sample_size)
        # 2. Get results (returned in order of ObjectiveFunction by default)
        population = self.read_performance_output()
        # DO AWAY WITH DICTIONARY STRUCTURE HERE
        # 3. Partition into complexes
        complxes: list[dict[str, pd.DataFrame]] = []
        for i in range(num_complexes):
            complx: dict[str, pd.DataFrame] = {}
            # Create one complex as a dictionary of dataframes
            for component, df in population.items():
                # Create a boolean mask to select rows of the i-th complex
                bool_mask = [(j % num_complexes) == i for j in range(len(df))]
                complx[component] = df.iloc[bool_mask]
            # 4. Implement CCE algorithm here on the complex
            complx = self._cce(complx, simplex_size, alpha)

