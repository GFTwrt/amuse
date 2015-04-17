import numpy

from amuse.support.exceptions import AmuseException
from amuse.datamodel import Particles, ParticlesOverlay
from amuse.units import units, quantities, constants

from amuse.ext.evrard_test import uniform_unit_sphere

def kudritzki_wind_velocity(mass, radius, luminosity, temperature, Y=0.25, I_He = 2):
    """
      This routine calculates the escape and terminal wind velocity. The Equations are taken
      from Kudritzki & Puls, Annual Reviews of Astronomy and Astrophysics, 2000, Vol. 38,
      p.613-666 Equation (8) and (9) and Kudritzki et al., 1989, A&A 219, 205 Equation (64)
      and (65).

      I_He:    Number of electrons per He nucleus (= 2 in O-Stars)
      sigma_e:   Thomson absorption coefficient
      Gamma:     Ratio of radiative Thomson to gravitational acceleration
    """
    sigma_e = 0.398 * (1 + I_He*Y)/(1 + 4*Y)
    Gamma = 7.66E-5 * sigma_e * luminosity.value_in(units.LSun)/ mass.value_in(units.MSun)
    v_esc = (2*constants.G * mass / radius*(1 - Gamma))**0.5

    condlist = [temperature >= 21000. | units.K,
                (10000. | units.K  < temperature) &  (temperature < 21000. | units.K),
                temperature <= 10000. | units.K]
    choicelist = [2.65, 1.4, 1.0]

    return v_esc * numpy.select(condlist, choicelist)

def as_three_vector(array):
    number = array
    if quantities.is_quantity(array):
        number = array.number
    three_vector = numpy.transpose([number]*3)
    if quantities.is_quantity(array):
        three_vector = three_vector | array.unit
    return three_vector

def random_positions(N, rmin, rmax):
    """
        The particles start out in a random position between
        the surface of the star and the distance that the
        previously released particles have reached.
        This assumes that the current wind velocity is
        comparable to the previous wind velocity.

        Note that the stellar position is not added yet here.
        TODO: consider optimizing this by making a large pool
        once, and draw positions from that.
    """
    random_positions = numpy.transpose(uniform_unit_sphere(N).make_xyz())
    vector_lengths = numpy.sqrt((random_positions**2).sum(1))

    unit_vectors = random_positions/as_three_vector(vector_lengths)

    distance = rmin + (vector_lengths * rmax)
    position = unit_vectors * as_three_vector(distance)

    return position, unit_vectors

class StarsWithMassLoss(Particles):
    def __init__(self, *args, **kwargs):
        super(StarsWithMassLoss, self).__init__(*args, **kwargs)
        self.collection_attributes.timestamp = 0. | units.yr
        self.collection_attributes.previous_time = 0. | units.yr
        self.collection_attributes.track_mechanical_energy = False

    def add_particles(self, particles, *args, **kwargs):
        new_particles = super(StarsWithMassLoss, self).add_particles(particles, *args, **kwargs)

        """
            TODO: there is a better way to define defaults
            override:
                can_extend_attributes
                set_value_in_store
                get_attribute_names_defined_in_store
                look at ParticlesWithFilteredAttributes as an example

        """

        attributes = particles.get_attribute_names_defined_in_store()
        if 'lost_mass' not in attributes:
            new_particles.lost_mass = 0. | units.MSun
        if 'wind_release_time' not in attributes:
            new_particles.wind_release_time = self.collection_attributes.timestamp
        if 'mu' not in attributes:
            new_particles.mu = self.collection_attributes.global_mu

        if self.collection_attributes.track_mechanical_energy:
            if 'mechanical_energy' not in attributes:
                new_particles.mechanical_energy = quantities.zero
            if 'previous_mechanical_luminosity' not in attributes:
                new_particles.previous_mechanical_luminosity = -1 | units.W
                self.collection_attributes.new_unset_lmech_particles = True

        return new_particles

    def evolve_mass_loss(self, time):
        if self.collection_attributes.previous_time > time:
            #TODO: do we really need this check? Why?
            return

        elapsed_time = time - self.collection_attributes.previous_time
        self.lost_mass += elapsed_time * self.wind_mass_loss_rate

        if self.collection_attributes.track_mechanical_energy:
            new_mechanical_luminosity = 0.5 * self.wind_mass_loss_rate * self.terminal_wind_velocity**2

            if self.collection_attributes.new_unset_lmech_particles:
                i_new = self.previous_mechanical_luminosity < quantities.zero
                self[i_new].previous_mechanical_luminosity = new_mechanical_luminosity[i_new]
                self.collection_attributes.new_unset_lmech_particles = False

            average_mechanical_luminosity = 0.5 * (self.previous_mechanical_luminosity + new_mechanical_luminosity)
            self.mechanical_energy += elapsed_time *average_mechanical_luminosity

            self.previous_mechanical_luminosity = new_mechanical_luminosity

        self.collection_attributes.timestamp = time
        self.collection_attributes.previous_time = time

    def track_mechanical_energy(self, track):
        self.collection_attributes.track_mechanical_energy = track

    def set_global_mu(self, mu):
        self.mu = mu
        self.collection_attributes.global_mu = mu

    def reset(self):
        self.lost_mass = 0.0|units.MSun
        self.set_begin_time(0.|units.yr)

    def set_begin_time(self, time):
        self.wind_release_time = time
        self.collection_attributes.timestamp = time
        self.collection_attributes.previous_time = time

class EvolvingStarsWithMassLoss(StarsWithMassLoss):
    """
        Derive the stellar wind from stellar evolution.
        You have to copy the relevant attributes from the stellar evolution.
        This can be done using a channel like:

        chan = stellar_evolution.particles.new_channel_to(stellar_wind.particles,
            attributes=["age", "radius", "mass", "luminosity", "temperature"])

        while <every timestep>:
            chan.copy()
    """
    def add_particles(self, particles, *args, **kwargs):
        new_particles = super(EvolvingStarsWithMassLoss, self).add_particles(particles, *args, **kwargs)
        attributes = particles.get_attribute_names_defined_in_store()
        if 'wind_mass_loss_rate' not in attributes:
            new_particles.wind_mass_loss_rate = 0. | units.MSun/units.yr
        if 'previous_age' not in attributes:
            new_particles.previous_age = new_particles.age
        if 'previous_mass' not in attributes:
            new_particles.previous_mass = new_particles.mass
        return new_particles

    def evolve_mass_loss(self, time):
        if self.collection_attributes.previous_time <= time:
            self.update_from_evolution()
            StarsWithMassLoss.evolve_mass_loss(self, time)

    def update_from_evolution(self):
        if (self.age != self.previous_age).any():
            mass_loss = self.previous_mass - self.mass
            timestep = self.age - self.previous_age
            self.wind_mass_loss_rate = mass_loss / timestep

            self.previous_age = self.age
            self.previous_mass = self.mass

class SimpleWind(object):
    """
        The simple wind model creates SPH particles moving away
        from the star at the terminal velocity.
        This is a safe assumption if the distance to other objects
        is (far) larger then the stellar radius.
    """
    def __init__(self, sph_particle_mass, derive_from_evolution=False, tag_gas_source=False):
        self.sph_particle_mass = sph_particle_mass
        self.model_time = 0.0|units.yr

        if derive_from_evolution:
            self.particles = EvolvingStarsWithMassLoss()
            self.particles.add_calculated_attribute("terminal_wind_velocity",
                kudritzki_wind_velocity,
                attributes_names=['mass', 'radius', 'luminosity', 'temperature'])
        else:
            self.particles = StarsWithMassLoss()

        self.target_gas = self.timestep = None
        self.tag_gas_source = tag_gas_source

        self.set_global_mu()
        self.internal_energy_formula = self.internal_energy_from_temperature

    def initial_wind_velocity(self, stars):
        return stars.terminal_wind_velocity

    def evolve_particles(self):
        self.particles.evolve_mass_loss(self.model_time)

    def evolve_model(self, time):
        if self.has_target():
            while self.model_time <= time:
                self.evolve_particles()
                if self.has_new_wind_particles():
                    wind_gas = self.create_wind_particles()
                    self.target_gas.add_particles(wind_gas)
                self.model_time += self.timestep
        else:
            self.model_time = time
            self.evolve_particles()

    def set_target_gas(self, target_gas, timestep):
        self.target_gas = target_gas
        self.timestep = timestep

    def has_target(self):
        return self.target_gas is not None

    def set_global_mu(self, Y=0.25, Z=0.02, x_ion=0.1):
        """
            Set the global value of mu used to create stellar wind.
            If the value of mu is known directly,
            use <stellar_wind>.particles.set_global_mu().
            An alternative way is to set mu for each star separately.
        """
        X = 1.0 - Y - Z
        mu = constants.proton_mass / (X*(1.0+x_ion) + Y*(1.0+2.0*x_ion)/4.0 + Z*x_ion/2.0)
        self.particles.set_global_mu(mu)

    def internal_energy_from_temperature(self, star, wind):
        """
            set the internal energy from the terminal wind stellar surface temperature.
        """
        return (3./2. * constants.kB * star.temperature / star.mu ) * 0.8

    def internal_energy_from_velocity(self, star, wind):
        """
            set the internal energy from the terminal wind velocity.
        """
        return 0.5 * star.terminal_wind_velocity**2

    def wind_sphere(self, star, Ngas):
        wind=Particles(Ngas)

        wind_velocity = self.initial_wind_velocity(star)
        outer_wind_distance = wind_velocity * (self.model_time - star.wind_release_time)

        wind.position, direction = random_positions(Ngas, star.radius, outer_wind_distance)
        wind.velocity = direction * wind_velocity

        return wind

    def create_wind_particles_for_one_star(self, star):
        Ngas = int(star.lost_mass/self.sph_particle_mass)
        star.lost_mass -= Ngas * self.sph_particle_mass

        wind = self.wind_sphere(star, Ngas)

        wind.mass = self.sph_particle_mass
        wind.u = self.internal_energy_formula(star, wind)
        wind.position += star.position
        wind.velocity += star.velocity

        if self.tag_gas_source:
            wind.source = star.key

        return wind

    def create_wind_particles(self):
        wind=Particles(0)

        for star in self.particles:
            if star.lost_mass > self.sph_particle_mass:
                new_particles = self.create_wind_particles_for_one_star(star)
                wind.add_particles(new_particles)
                star.wind_release_time = self.model_time

        return wind

    def has_new_wind_particles(self):
        return self.particles.lost_mass.max() > self.sph_particle_mass

    def create_initial_wind(self, number=None, time=None, check_length=True):
        """
            This is a convenience method that creates some initial particles.
            They are created as if the wind has already been blowing for 'time'.
            Note that this does not work if the mass loss is derived from stellar evolution.

            If 'number' is given, the required time to get that number of particles
            is calculated. This assumes that the number of expected particles
            is far larger then the number of stars
        """
        if not number is None:
            required_mass = number * self.sph_particle_mass
            total_mass_loss = self.particles.wind_mass_loss_rate.sum()
            time = 1.1 * required_mass/total_mass_loss

        self.model_time = time
        self.particles.evolve_mass_loss(self.model_time)

        if self.has_new_wind_particles():
            wind_gas = self.create_wind_particles()
            if self.has_target():
                self.target_gas.add_particles(wind_gas)
        elif check_length :
            raise AmuseException("create_initial_wind time was too small to create any particles.")
        else:
            wind_gas = Particles()

        self.reset()

        return wind_gas

    def reset(self):
        self.particles.reset()
        self.model_time = 0.0|units.yr

    def set_begin_time(self, time):
        self.model_time = time
        self.particles.set_begin_time(time)

    def get_gravity_at_point(self, eps, x, y, z):
        return [0, 0, 0]|units.m/units.s**2

    def get_potential_at_point(self, radius, x, y, z):
        return [0, 0, 0]|units.J

class AcceleratingWind(SimpleWind):
    """
       This wind model returns SPH particles moving away from the star at sub terminal velocity.
       It also adds a potential around the star that represents the radiation pressure.
       This potential can accelerate all particles away from the star using bridge.
       This is good for simulating processes within a few stellar radii.
    """

    def __init__(self, *args, **kwargs):
        self.init_v_wind_velocity = kwargs.pop("init_v_wind_velocity", 5.0 | units.kms)
        self.r_min_ratio = kwargs.pop("r_min_ratio", 1)
        self.r_max_ratio = kwargs.pop("r_max_ratio", 5)
        self.wind_accelation_formula = self.one_over_r_squared_wind_accelation_formula
        super(AcceleratingWind, self).__init__(*args, **kwargs)

    def initial_wind_velocity(self, stars):
        # escape_velocity_at_surface = (2*constants.G * stars.mass / stars.radius)**0.5
        return self.init_v_wind_velocity

    def one_over_r_squared_wind_accelation_formula(self, star, distance):
        """
            A simple formula that approximates acceleration due to
            radiation pressure at a given distance from the star.
        """

        r_min = self.r_min_ratio * star.radius
        r_max = self.r_max_ratio * star.radius
        init_wind_velocity = self.initial_wind_velocity(star)
        integrated_gravity_acceleration = constants.G * star.mass * (r_min**-1 - r_max**-1)
        integrated_acceleration = 0.5 * ( star.terminal_wind_velocity**2 - init_wind_velocity**2 ) + integrated_gravity_acceleration
        scaling_constant = integrated_acceleration / (r_min**-1 - r_max**-1)

        radii_in_range = numpy.logical_and(distance > r_min, distance < r_max)

        acceleration = numpy.zeros(distance.shape) | units.m/units.s**2
        acceleration[radii_in_range] = scaling_constant * distance[radii_in_range]**-2

        return acceleration

    def first_constant_then_one_over_r_squared_wind_accelation_formula(self, star, distance):
        """
            A slighly more complex formula that approximates acceleration due to
            radiation pressure at a given distance from the star.
        """
        r_star = star.radius
        r_min = self.r_min_ratio * r_star
        r_max = self.r_max_ratio * r_star

        const_integrated_gravity_acceleration = constants.G * star.mass * (r_star**-1 - r_min**-1)
        const_scaling_constant = const_integrated_acceleration / (r_star**-1 - r_min**-1)
        const_radii_in_range = numpy.logical_and(distance > r_star, distance < r_min)

        init_wind_velocity = self.initial_wind_velocity(star)
        integrated_gravity_acceleration = constants.G * star.mass * (r_min**-1 - r_max**-1)
        integrated_acceleration = 0.5 * ( star.terminal_wind_velocity**2 - init_wind_velocity**2 ) + integrated_gravity_acceleration
        scaling_constant = integrated_acceleration / (r_min**-1 - r_max**-1)

        radii_in_range = numpy.logical_and(distance > r_min, distance < r_max)

        acceleration = numpy.zeros(distance.shape) | units.m/units.s**2
        acceleration[radii_in_range] = scaling_constant * distance[radii_in_range]**-2
        acceleration[const_radii_in_range] = const_scaling_constant * distance[const_radii_in_range]**-2

        return acceleration

    def get_gravity_at_point(self, eps, x, y, z):
        total_acceleration = numpy.zeros(shape=(len(x), 3))|units.m/units.s**2

        positions = quantities.as_vector_quantity(numpy.transpose([x, y, z]))
        for star in self.particles:
            relative_position = positions - star.position
            distance = relative_position.lengths()
            acceleration = self.wind_accelation_formula(star, distance)
            direction = relative_position / as_three_vector(distance)
            # Correct for directionless vectors with length 0
            direction[numpy.isnan(direction)] = 0
            total_acceleration += direction * as_three_vector(acceleration)

        return total_acceleration.transpose()

class MechanicalLuminosityWind(SimpleWind):
    """
        This wind model returns SPH particles that have no initial velocity with respect to the star.
        The energy of the integrated mechanical luminosity is added as internal energy.
        This is a numerical integration, so the timescale with which evolve_model
        is called should be small enough for convergence.

        This method good for simulating processes far from the star,
        and when the SPH particle mass is larger then the stellar mass loss per timestep.
        It can make a big difference when the wind is derived from evolution.
    """

    def __init__(self, *args, **kwargs):
        self.feedback_efficiency = kwargs.pop("feedback_efficiency", 0.01)
        self.r_max = kwargs.pop("r_max", None)
        self.r_max_ratio = kwargs.pop("r_max_ratio", 5)
        super(MechanicalLuminosityWind, self).__init__(*args, **kwargs)

        self.internal_energy_formula = self.mechanical_internal_energy

        self.previous_time = 0|units.Myr
        self.particles.track_mechanical_energy(True)

    def evolve_particles(self):
        self.particles.evolve_mass_loss(self.model_time)

    def mechanical_internal_energy(self, star, wind):
        mass_lost = wind.mass.sum()
        mechanical_energy_to_remove = star.mechanical_energy / (star.lost_mass/mass_lost + 1)
        star.mechanical_energy -= mechanical_energy_to_remove

        return self.feedback_efficiency * mechanical_energy_to_remove / mass_lost

    def wind_sphere(self, star, Ngas):
        wind=Particles(Ngas)

        r_max = self.r_max or self.r_max_ratio * star.radius
        wind.position, direction = random_positions(Ngas, star.radius, r_max)
        wind.velocity = [0, 0, 0] | units.kms

        return wind

    def reset(self):
        super(MechanicalLuminosityWind, self).reset()
        self.previous_time = 0|units.Myr

wind_modes = {"simple": SimpleWind,
              "accelerate": AcceleratingWind,
              "mechanical": MechanicalLuminosityWind,
              }
def new_stellar_wind(sph_particle_mass, target_gas=None, timestep=None, derive_from_evolution=False, mode="simple", **kwargs):
    """
        Create a new stellar wind code.
        target_gas: a gas particle set into which the wind particles should be put (requires timestep)
        timestep: the timestep at which the wind particles should be generated.
        derive_from_evolution: derive the wind parameters from stellar evolution (you still need to update the stellar parameters)
        mode: set to 'simple', 'accelerate' or 'mechanical'
    """
    if (target_gas is None) ^ (timestep is None):
        raise AmuseException("Must specify both target_gas and timestep (or neither)")

    stellar_wind = wind_modes[mode](sph_particle_mass, derive_from_evolution, **kwargs)

    if target_gas is not None:
        stellar_wind.set_target_gas(target_gas, timestep)

    return stellar_wind

def static_wind_from_stellar_evolution(stellar_wind, stellar_evolution, start_time, end_time):
    """
        Convenience method that sets up the stellar wind parameters using a stellar evolution code.
        The change in the stars between start_time and end_time determines the stellar wind.
        Do not add the star particles to the stellar_wind code before this.
    """
    stellar_evolution.evolve_model(start_time)
    stellar_wind.particles.add_particles(stellar_evolution.particles)

    stellar_evolution.evolve_model(end_time)
    chan = stellar_evolution.particles.new_channel_to(stellar_wind.particles)
    chan.copy_attributes(["age", "radius", "mass", "luminosity", "temperature"])

    #TODO: shouldn't this be stellar_wind.reset()
    stellar_wind.evolve_model(0|units.yr)

    return stellar_wind
