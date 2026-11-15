// Clavius independent NASA Glenn-inspired wheel rig using Project Chrono SCM.
// The upstream API examples are BSD-3-Clause; retained license is in third_party/.
// Published rig dimensions are factual inputs. Soil values are declared scenarios.
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <set>

#include "chrono/collision/bullet/ChCollisionSystemBullet.h"
#include "chrono/collision/ChCollisionShapeBox.h"
#include "chrono/collision/ChCollisionShapeCylinder.h"
#include "chrono/functions/ChFunctionRamp.h"
#include "chrono/physics/ChBody.h"
#include "chrono/physics/ChLinkLock.h"
#include "chrono/physics/ChLinkMotorLinearPosition.h"
#include "chrono/physics/ChLinkMotorRotationAngle.h"
#include "chrono/physics/ChSystemSMC.h"
#include "chrono/solver/ChIterativeSolver.h"
#include "chrono_vehicle/terrain/SCMTerrain.h"
#include "chrono_thirdparty/rapidjson/document.h"
#include "chrono_thirdparty/rapidjson/istreamwrapper.h"

using namespace chrono;

double numeric(const rapidjson::Document& d, const char* key, double low, double high) {
    if (!d.HasMember(key) || !d[key].IsNumber()) throw std::runtime_error(std::string("Missing numeric field: ")+key);
    double value = d[key].GetDouble();
    if (!std::isfinite(value) || value < low || value > high) throw std::runtime_error(std::string("Out-of-range field: ")+key);
    return value;
}

int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::runtime_error("Usage: clavius_chrono_reference input.json trace.csv");
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("Cannot open input");
        rapidjson::IStreamWrapper wrapper(input);
        rapidjson::Document d;
        d.ParseStream(wrapper);
        if (d.HasParseError() || !d.IsObject()) throw std::runtime_error("Invalid configuration JSON");
        const std::set<std::string> allowed = {"slip", "dt_s", "grid_m", "duration_s", "gravity_m_s2", "bekker_kphi", "bekker_kc", "bekker_n", "cohesion_pa", "friction_angle_deg", "janosi_m", "elastic_pa_m", "damping_pa_s_m", "bulldozing"};
        for (auto it=d.MemberBegin(); it!=d.MemberEnd(); ++it) {
            if (!allowed.count(it->name.GetString())) throw std::runtime_error("Unknown configuration field");
        }
        const double slip=numeric(d,"slip",-.01,.9), dt=numeric(d,"dt_s",1e-5,.005);
        const double grid=numeric(d,"grid_m",.001,.04), duration=numeric(d,"duration_s",.1,30);
        const double gravity=numeric(d,"gravity_m_s2",.1,12);
        const double kphi=numeric(d,"bekker_kphi",1e3,1e8), kc=numeric(d,"bekker_kc",0,1e6), n=numeric(d,"bekker_n",.5,2);
        const double cohesion=numeric(d,"cohesion_pa",0,1e4), phi=numeric(d,"friction_angle_deg",1,60), janosi=numeric(d,"janosi_m",1e-4,.2);
        const double elastic=numeric(d,"elastic_pa_m",kphi,1e10), damping=numeric(d,"damping_pa_s_m",0,1e7);
        if (!d.HasMember("bulldozing") || !d["bulldozing"].IsBool()) throw std::runtime_error("Missing bulldozing boolean");
        const double radius=.25, width=.2, grouser_height=.025, grouser_width=.005;
        const int grouser_count=24;
        const double half_load=17.5/2, velocity=.2, omega=velocity/(radius*(1-slip));
        ChSystemSMC sys;
        sys.SetGravitationalAcceleration(ChVector3d(0,0,-gravity));
        sys.SetNumThreads(1,1,1);
        sys.SetCollisionSystem(chrono_types::make_shared<ChCollisionSystemBullet>());
        sys.SetSolverType(ChSolver::Type::MINRES);
        sys.SetTimestepperType(ChTimestepper::Type::EULER_IMPLICIT_LINEARIZED);
        auto solver=std::dynamic_pointer_cast<ChIterativeSolver>(sys.GetSolver());
        if(!solver) throw std::runtime_error("Expected iterative native solver");
        solver->SetMaxIterations(200);
        solver->SetTolerance(1e-10);

        auto fixed=chrono_types::make_shared<ChBody>();
        fixed->SetFixed(true);
        sys.AddBody(fixed);
        const ChVector3d start(-2.1,0,radius+.005);
        auto carriage=chrono_types::make_shared<ChBody>();
        carriage->SetMass(half_load); carriage->SetInertiaXX(ChVector3d(.1,.1,.1)); carriage->SetPos(start);
        sys.AddBody(carriage);
        auto linear=chrono_types::make_shared<ChLinkMotorLinearPosition>();
        linear->Initialize(carriage,fixed,ChFrame<>(start,QuatFromAngleY(CH_PI_2)));
        linear->SetMotionFunction(chrono_types::make_shared<ChFunctionRamp>(0,velocity));
        sys.AddLink(linear);
        auto axle=chrono_types::make_shared<ChBody>();
        axle->SetMass(half_load); axle->SetInertiaXX(ChVector3d(.1,.1,.1)); axle->SetPos(start);
        sys.AddBody(axle);
        auto vertical=chrono_types::make_shared<ChLinkLockPrismatic>();
        vertical->Initialize(axle,carriage,ChFrame<>(start,QUNIT));
        sys.AddLink(vertical);
        auto wheel=chrono_types::make_shared<ChBody>();
        wheel->SetMass(half_load); wheel->SetPos(start);
        const double transverse=half_load*(3*radius*radius+width*width)/12;
        wheel->SetInertiaXX(ChVector3d(transverse,half_load*radius*radius/2,transverse));
        auto material=chrono_types::make_shared<ChContactMaterialSMC>();
        auto core=chrono_types::make_shared<ChCollisionShapeCylinder>(material,radius-grouser_height,width);
        wheel->AddCollisionShape(core,ChFrame<>(VNULL,QuatFromAngleX(CH_PI_2)));
        for(int i=0;i<grouser_count;i++) {
            double angle=2*CH_PI*i/grouser_count;
            double center=radius-grouser_height/2;
            auto box=chrono_types::make_shared<ChCollisionShapeBox>(material,grouser_width,width,grouser_height);
            wheel->AddCollisionShape(box,ChFrame<>(ChVector3d(center*std::sin(angle),0,center*std::cos(angle)),QuatFromAngleY(angle)));
        }
        wheel->EnableCollision(true);
        sys.AddBody(wheel);
        auto motor=chrono_types::make_shared<ChLinkMotorRotationAngle>();
        motor->Initialize(wheel,axle,ChFrame<>(start,QuatFromAngleX(-CH_PI_2)));
        motor->SetAngleFunction(chrono_types::make_shared<ChFunctionRamp>(0,omega));
        sys.AddLink(motor);

        vehicle::SCMTerrain terrain(&sys,false);
        terrain.SetSoilParameters(kphi,kc,n,cohesion,phi,janosi,elastic,damping);
        terrain.Initialize(9.,1.,grid);
        terrain.EnableBulldozing(d["bulldozing"].GetBool());
        if(d["bulldozing"].GetBool()) terrain.SetBulldozingParameters(55,1,5,6);
        terrain.AddMovingPatch(wheel,VNULL,ChVector3d(.6,.25,.6));
        // Match initial commanded velocities to avoid an artificial start impulse.
        carriage->SetPosDt(ChVector3d(velocity,0,0));
        axle->SetPosDt(ChVector3d(velocity,0,0));
        wheel->SetPosDt(ChVector3d(velocity,0,0));
        wheel->SetAngVelParent(ChVector3d(0,omega,0));

        std::ofstream trace(argv[2]);
        if(!trace) throw std::runtime_error("Cannot create trace");
        trace<<std::setprecision(17);
        trace<<"time_s,x_m,z_m,vx_m_s,vz_m_s,omega_rad_s,terrain_force_x_n,terrain_force_z_n,terrain_torque_y_nm,linear_motor_force_n,spin_motor_torque_nm,center_sinkage_m,center_plastic_sinkage_m,ray_hits\n";
        int steps=std::lround(duration/dt), stride=std::max(1,static_cast<int>(std::lround(.01/dt)));
        for(int i=0;i<steps;i++) {
            sys.DoStepDynamics(dt);
            if(!std::isfinite(wheel->GetPos().z()) || wheel->GetPos().z() < -.3 || wheel->GetPos().z() > 1) throw std::runtime_error("Unstable or unsupported wheel state");
            if(i%stride==0 || i==steps-1) {
                ChVector3d force(0), torque(0);
                terrain.GetContactForceBody(wheel,force,torque);
                auto node=terrain.GetNodeInfo(wheel->GetPos());
                trace<<sys.GetChTime()<<','<<wheel->GetPos().x()<<','<<wheel->GetPos().z()<<','<<wheel->GetPosDt().x()<<','<<wheel->GetPosDt().z()<<','<<wheel->GetAngVelParent().y()<<','<<force.x()<<','<<force.z()<<','<<torque.y()<<','<<linear->GetMotorForce()<<','<<motor->GetMotorTorque()<<','<<node.sinkage<<','<<node.sinkage_plastic<<','<<terrain.GetNumRayHits()<<'\n';
            }
        }
        trace.flush();
        if(!trace) throw std::runtime_error("Trace write failed");
        std::cout<<"Completed native Chrono "<<CHRONO_VERSION<<" SCM reference; steps="<<steps<<" grid_m="<<grid<<"\n";
    } catch(const std::exception& e) {
        std::cerr<<"CLAVIUS_CHRONO_ERROR: "<<e.what()<<'\n';
        return 1;
    }
    return 0;
}
