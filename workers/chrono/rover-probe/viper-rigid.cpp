// Bounded component probe of the original upstream VIPER model.
// Ideal wheel-speed actuation on a declared rigid floor is not flight capability.
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include "chrono/physics/ChSystemSMC.h"
#include "chrono/physics/ChBodyEasy.h"
#include "chrono/solver/ChIterativeSolver.h"
#include "chrono_models/robot/viper/Viper.h"

using namespace chrono;
using namespace chrono::viper;

class ProbeDriver: public ViperDriver {
  public:
    virtual DriveMotorType GetDriveMotorType() const override { return DriveMotorType::SPEED; }
    virtual void Update(double time) override {
        const double speed=.4*std::max(0.,std::min(1.,time-3.));
        drive_speeds={speed,speed,speed,speed};
    }
};

int main(int argc,char** argv) {
    try {
        if(argc!=5) throw std::runtime_error("Usage: clavius_viper_rigid_probe chrono-data gravity dt trace.csv");
        const double gravity=std::stod(argv[2]),dt=std::stod(argv[3]);
        if((gravity!=9.81 && gravity!=1.62) || (dt!=.001 && dt!=.0005)) throw std::runtime_error("Only declared probe gravities/steps are supported");
        SetChronoDataPath(std::string(argv[1])+"/");
        ChSystemSMC sys;
        sys.SetNumThreads(1,1,1);
        sys.SetCollisionSystemType(ChCollisionSystem::Type::BULLET);
        sys.SetGravitationalAcceleration(ChVector3d(0,0,-gravity));
        sys.SetSolverType(ChSolver::Type::MINRES);
        sys.SetTimestepperType(ChTimestepper::Type::EULER_IMPLICIT_LINEARIZED);
        auto solver=std::dynamic_pointer_cast<ChIterativeSolver>(sys.GetSolver());
        solver->SetMaxIterations(300);solver->SetTolerance(1e-10);
        auto material=chrono_types::make_shared<ChContactMaterialSMC>();
        material->SetFriction(.7);material->SetRestitution(0);material->SetYoungModulus(2e7);
        auto floor=chrono_types::make_shared<ChBodyEasyBox>(20,10,.2,1000,false,true,material);
        floor->SetFixed(true);floor->SetPos(ChVector3d(0,0,-.1));sys.AddBody(floor);
        auto driver=chrono_types::make_shared<ProbeDriver>();
        Viper rover(&sys,ViperWheelType::RealWheel);
        rover.SetChassisVisualization(false);rover.SetWheelVisualization(false);rover.SetSuspensionVisualization(false);
        rover.SetWheelContactMaterial(material);rover.SetDriver(driver);
        rover.Initialize(ChFrame<>(ChVector3d(0,0,.3),QUNIT));
        double mass=0;
        for(const auto& body:sys.GetBodies()) if(!body->IsFixed()) mass+=body->GetMass();
        std::ofstream trace(argv[4]);if(!trace) throw std::runtime_error("Cannot write trace");
        trace<<std::setprecision(17)<<"time_s,x_m,y_m,z_m,vx_m_s,vy_m_s,vz_m_s,normal_force_n,drive_torque_sum_nm,wheel_mean_omega_rad_s,chassis_qw,chassis_qx,chassis_qy,chassis_qz\n";
        const int steps=std::lround(20/dt),stride=std::lround(.01/dt);
        for(int i=0;i<steps;i++) {
            rover.Update();sys.DoStepDynamics(dt);
            const auto pos=rover.GetChassisPos(),vel=rover.GetChassisVel();
            const auto q=rover.GetChassisRot();
            if(!std::isfinite(pos.z()) || pos.z() < -.2 || pos.z()>1.) throw std::runtime_error("Unstable or unsupported assembled rover state");
            if(i%stride==0 || i==steps-1) {
                double normal=0,torque=0,omega=0;
                for(int j=0;j<4;j++) {
                    auto id=static_cast<ViperWheelID>(j);
                    normal+=rover.GetWheelContactForce(id).z();
                    torque+=rover.GetWheelTracTorque(id);
                    omega+=rover.GetWheel(id)->GetBody()->GetAngVelParent().y()/4;
                }
                trace<<sys.GetChTime()<<','<<pos.x()<<','<<pos.y()<<','<<pos.z()<<','<<vel.x()<<','<<vel.y()<<','<<vel.z()<<','<<normal<<','<<torque<<','<<omega<<','<<q.e0()<<','<<q.e1()<<','<<q.e2()<<','<<q.e3()<<'\n';
            }
        }
        trace.flush();if(!trace)throw std::runtime_error("Trace write failed");
        std::cout<<std::setprecision(17)<<"Original upstream VIPER rigid probe completed; mass_kg="<<mass<<" gravity_m_s2="<<gravity<<" dt_s="<<dt<<'\n';
    } catch(const std::exception& error) {
        std::cerr<<"CLAVIUS_ROVER_PROBE_ERROR: "<<error.what()<<'\n';return 1;
    }
}
