// Recorded component experiment on the same local DEM facets as the browser.
#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <stdexcept>
#include <vector>
#include <iostream>
#include "Viper.h"
#include "chrono/physics/ChSystemSMC.h"
#include "chrono/geometry/ChTriangleMeshConnected.h"
#include "chrono/collision/ChCollisionShapeTriangleMesh.h"
#include "chrono/solver/ChIterativeSolver.h"

using namespace chrono;
using namespace chrono::clavius_viper;

class Driver : public ViperDriver {
  public:
    explicit Driver(bool crab) : crab(crab) {}
    DriveMotorType GetDriveMotorType() const override { return DriveMotorType::SPEED; }
    void Update(double time) override {
        double omega = .4 * std::clamp(time-3.,0.,1.);
        drive_speeds = {omega,omega,omega,omega};
        if (crab) {
            // The two rear steering motor frames are reversed in the source assembly.
            const double ramp = std::clamp((time - 1.) / 2., 0., 1.);
            const double angle = 25. * CH_PI / 180. * ramp;
            steer_angles = {angle, angle, -angle, -angle};
        }
    }
  private:
    bool crab;
};

int main(int argc, char** argv) {
  try {
    if (argc < 4 || argc > 6 || (argc >= 5 && std::string(argv[4]) != "straight" && std::string(argv[4]) != "crab"))
        throw std::runtime_error("Usage: clavius_site_drive chrono-data drive-grid.bin frames.bin [straight|crab [wheel-states.bin]]");
    SetChronoDataPath(std::string(argv[1])+"/");
    std::vector<float> grid(513*513);
    std::ifstream input(argv[2], std::ios::binary);
    if (!input.read(reinterpret_cast<char*>(grid.data()), grid.size()*sizeof(float)) || input.peek()!=EOF)
        throw std::runtime_error("Expected 513 by 513 float32 grid");
    auto point = [&](int i,int j) { return ChVector3d(5.*i,5.*j,grid[(256+j)*513+256+i]); };
    ChSystemSMC sys;
    sys.SetNumThreads(1,1,1);
    sys.SetCollisionSystemType(ChCollisionSystem::Type::BULLET);
    sys.SetGravitationalAcceleration({0,0,-1.62});
    sys.SetSolverType(ChSolver::Type::MINRES);
    sys.SetTimestepperType(ChTimestepper::Type::EULER_IMPLICIT_LINEARIZED);
    auto solver=std::dynamic_pointer_cast<ChIterativeSolver>(sys.GetSolver());
    solver->SetMaxIterations(300);solver->SetTolerance(1e-10);
    auto material=chrono_types::make_shared<ChContactMaterialSMC>();
    material->SetFriction(.7);material->SetRestitution(0);material->SetYoungModulus(2e7);
    auto mesh=chrono_types::make_shared<ChTriangleMeshConnected>();
    for(int j=-2;j<2;j++) for(int i=-2;i<2;i++) {
        mesh->AddTriangle(point(i,j),point(i+1,j),point(i,j+1));
        mesh->AddTriangle(point(i+1,j),point(i+1,j+1),point(i,j+1));
    }
    auto floor=chrono_types::make_shared<ChBody>();floor->SetFixed(true);
    floor->AddCollisionShape(chrono_types::make_shared<ChCollisionShapeTriangleMesh>(material,mesh,true,false,0.));
    floor->EnableCollision(true);sys.AddBody(floor);
    Viper rover(&sys,ViperWheelType::RealWheel);
    rover.SetChassisVisualization(false);rover.SetWheelVisualization(false);rover.SetSuspensionVisualization(false);
    rover.SetWheelContactMaterial(material);rover.SetDriver(chrono_types::make_shared<Driver>(argc >= 5 && std::string(argv[4]) == "crab"));
    rover.Initialize(ChFrame<>(point(0,0)+ChVector3d(0,0,.52),QUNIT));
    std::vector<std::shared_ptr<ChBodyAuxRef>> bodies={rover.GetChassis()->GetBody()};
    for(int i=0;i<4;i++) {
        auto id=static_cast<ViperWheelID>(i);
        bodies.insert(bodies.end(),{rover.GetUpperArm(id)->GetBody(),rover.GetLowerArm(id)->GetBody(),
                      rover.GetUpright(id)->GetBody(),rover.GetWheel(id)->GetBody()});
    }
    std::ofstream out(argv[3],std::ios::binary);
    std::ofstream wheel_states;
    if (argc == 6) {
        wheel_states.open(argv[5], std::ios::binary);
        if (!wheel_states) throw std::runtime_error("Cannot open wheel telemetry output");
    }
    double normal=0;int force_samples=0;
    for(int step=0;step<=20000;step++) {
        if (step > 0 && argc == 6) {
            for (int i = 0; i < 4; ++i) {
                const auto id = static_cast<ViperWheelID>(i);
                const auto& frame = rover.GetWheel(id)->GetBody()->GetFrameRefToAbs();
                const std::array<ChVector3d,5> state = {
                    frame.GetPos(), rover.GetWheelLinVel(id), rover.GetWheelAngVel(id),
                    frame.GetRot().Rotate(ChVector3d(0,1,0)), rover.GetWheelContactForce(id)
                };
                for (const auto& v : state) {
                    const std::array<float,3> xyz = {float(v.x()),float(v.y()),float(v.z())};
                    wheel_states.write(reinterpret_cast<const char*>(xyz.data()),sizeof(xyz));
                }
            }
        }
        if(step%50==0){
            for(const auto& b:bodies){
                const auto& f=b->GetFrameRefToAbs();auto p=f.GetPos();auto q=f.GetRot();
                std::array<float,7> row={float(p.x()),float(p.y()),float(p.z()),float(q.e1()),float(q.e2()),float(q.e3()),float(q.e0())};
                for(auto x:row)if(!std::isfinite(x))throw std::runtime_error("Non-finite body state");
                out.write(reinterpret_cast<const char*>(row.data()),sizeof(row));
            }
            auto p=rover.GetChassisPos();
            if(std::abs(p.x())>8||std::abs(p.y())>8||std::abs(p.z())>2)throw std::runtime_error("Rover left experiment volume");
            if(step>=10000){
                for(int i=0;i<4;i++)normal+=rover.GetWheelContactForce(static_cast<ViperWheelID>(i)).z();
                force_samples++;
            }
        }
        if(step<20000){rover.Update();sys.DoStepDynamics(.001);}
    }
    if (argc == 6) { wheel_states.close(); if (!wheel_states) throw std::runtime_error("Wheel telemetry write failed"); }
    out.close();if(!out)throw std::runtime_error("Trace write failed");
    const double support=normal/(force_samples*rover.GetRoverMass()*1.62);
    if(support<.85||support>1.15||rover.GetChassisPos().x()<.6)throw std::runtime_error("Support or forward progress check failed");
    std::cout<<"Forward displacement (m) "<<rover.GetChassisPos().x()<<" mean vertical support / weight "<<support<<std::endl;
  }catch(const std::exception& error){std::cerr<<error.what()<<std::endl;return 1;}
}
