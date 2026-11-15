// Clavius component checks of the repaired CAD mass/shaft frames.
// Compares actual body tensors to independently transformed original colliders.
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include "chrono/physics/ChSystemSMC.h"
#include "chrono/physics/ChShaftBodyConstraint.h"
#include "chrono/geometry/ChTriangleMeshConnected.h"
#include "chrono/solver/ChIterativeSolver.h"
#include "chrono_thirdparty/rapidjson/ostreamwrapper.h"
#include "chrono_thirdparty/rapidjson/prettywriter.h"
#ifdef CLAVIUS_ORIGINAL
#include "chrono_models/robot/viper/Viper.h"
using namespace chrono::viper;
const char* variant="upstream-original";
#else
#include "Viper.h"
using namespace chrono::clavius_viper;
const char* variant="clavius-frame-repaired";
#endif
using namespace chrono;

class ConstantTorqueDriver:public ViperDriver {
 public:
  DriveMotorType GetDriveMotorType() const override {return DriveMotorType::TORQUE;}
  void Update(double) override {
    for(int i=0;i<4;i++)viper->GetDriveshaft(static_cast<ViperWheelID>(i))->SetAppliedLoad(-1.0);
  }
};

int main(int argc,char** argv) {
 try {
  if(argc!=5)throw std::runtime_error("Usage: frames chrono-data static|torque|wrong-axis identity|tilted output.json");
  const std::string mode=argv[2],pose=argv[3];
  if(mode!="static"&&mode!="torque"&&mode!="wrong-axis")throw std::runtime_error("Unsupported check mode");
  if(pose!="identity"&&pose!="tilted")throw std::runtime_error("Unsupported pose");
#ifdef CLAVIUS_ORIGINAL
  if(mode=="wrong-axis")throw std::runtime_error("Wrong-axis control requires repaired model");
#endif
  SetChronoDataPath(std::string(argv[1])+"/");
  ChSystemSMC sys;
  sys.SetNumThreads(1,1,1);sys.SetCollisionSystemType(ChCollisionSystem::Type::BULLET);
  sys.SetGravitationalAcceleration(VNULL);
  sys.SetSolverType(ChSolver::Type::MINRES);
  sys.SetTimestepperType(ChTimestepper::Type::EULER_IMPLICIT_LINEARIZED);
  auto solver=std::dynamic_pointer_cast<ChIterativeSolver>(sys.GetSolver());
  solver->SetMaxIterations(300);solver->SetTolerance(1e-10);
  std::shared_ptr<ViperDriver> driver;
  if(mode=="static")driver=chrono_types::make_shared<ViperSpeedDriver>(1,0);
  else driver=chrono_types::make_shared<ConstantTorqueDriver>();
  Viper rover(&sys,ViperWheelType::RealWheel);
  rover.SetChassisFixed(true);rover.SetDriver(driver);
  rover.SetChassisVisualization(false);rover.SetWheelVisualization(false);rover.SetSuspensionVisualization(false);
  const auto rotation=pose=="identity"?QUNIT:QuatFromAngleZ(.7)*QuatFromAngleY(-.15)*QuatFromAngleX(.2);
  rover.Initialize(ChFrame<>(ChVector3d(1.2,-.4,.8),rotation));
  rover.Update();sys.Update(false);
  std::vector<std::shared_ptr<ChShaftBodyRotation>> couplings;
  for(const auto& item:sys.GetOtherPhysicsItems()) {
    auto coupling=std::dynamic_pointer_cast<ChShaftBodyRotation>(item);
    if(coupling) {
      if(mode=="wrong-axis")coupling->SetShaftDirection(ChVector3d(0,0,-1));
      couplings.push_back(coupling);
    }
  }
  if(couplings.size()!=4)throw std::runtime_error("Expected four native shaft-body constraints");
  double max_constraint=0,max_shaft_speed_error=0;
  auto sample=[&]() {
    for(const auto& link:sys.GetLinks()) {
      auto c=link->GetConstraintViolation();
      if(c.size())max_constraint=std::max(max_constraint,c.cwiseAbs().maxCoeff());
    }
    for(int i=0;i<4;i++) {
      auto id=static_cast<ViperWheelID>(i);auto body=rover.GetWheel(id)->GetBody();
      auto omega_ref=body->GetFrameRefToAbs().TransformDirectionParentToLocal(body->GetAngVelParent());
      max_shaft_speed_error=std::max(max_shaft_speed_error,std::abs(rover.GetDriveshaft(id)->GetPosDt()+omega_ref.y()));
    }
  };
  sample();
  if(mode!="static")for(int step=0;step<400;step++){rover.Update();sys.DoStepDynamics(.0005);sample();}
  std::ofstream output(argv[4]);if(!output)throw std::runtime_error("Cannot create evidence");
  rapidjson::OStreamWrapper stream(output);rapidjson::PrettyWriter<rapidjson::OStreamWrapper> w(stream);
  auto vec=[&](const ChVector3d& v){w.StartArray();w.Double(v.x());w.Double(v.y());w.Double(v.z());w.EndArray();};
  auto matrix=[&](const ChMatrix33<>& m){w.StartArray();for(int i=0;i<3;i++){w.StartArray();for(int j=0;j<3;j++)w.Double(m(i,j));w.EndArray();}w.EndArray();};
  double all_mass=0;for(const auto& body:sys.GetBodies())all_mass+=body->GetMass();
  w.StartObject();w.Key("variant");w.String(variant);w.Key("mode");w.String(mode.c_str());w.Key("pose");w.String(pose.c_str());
  w.Key("native_time_s");w.Double(sys.GetChTime());w.Key("all_body_mass_kg");w.Double(all_mass);
  w.Key("reported_rover_mass_kg");w.Double(rover.GetRoverMass());
  w.Key("maximum_joint_constraint_residual");w.Double(max_constraint);
  w.Key("maximum_shaft_speed_relation_error_rad_s");w.Double(max_shaft_speed_error);
  w.Key("wheels");w.StartArray();
  for(int i=0;i<4;i++) {
    auto id=static_cast<ViperWheelID>(i);auto body=rover.GetWheel(id)->GetBody();
    const bool left=id==V_LF||id==V_LB;
    auto mesh=ChTriangleMeshConnected::CreateFromWavefrontFile(GetChronoDataFile("robot/viper/col/viper_wheel.obj"),false,false);
    mesh->Transform(VNULL,ChMatrix33<>(left?QuatFromAngleZ(CH_PI):QUNIT));mesh->RepairDuplicateVertexes(1e-9);
    double volume;ChVector3d expected_cog;ChMatrix33<> expected_inertia;
    mesh->ComputeMassProperties(true,volume,expected_cog,expected_inertia);expected_inertia*=800;
    auto frame=body->GetFrameCOMToRef();
    ChMatrix33<> actual_inertia=frame.GetRotMat()*body->GetInertia()*frame.GetRotMat().transpose();
    auto omega=body->GetFrameRefToAbs().TransformDirectionParentToLocal(body->GetAngVelParent());
    std::shared_ptr<ChShaftBodyRotation> coupling;
    for(const auto& candidate:couplings)if(candidate->GetBody()==body.get())coupling=candidate;
    if(!coupling)throw std::runtime_error("Missing native wheel shaft");
    auto axis_world=body->TransformDirectionLocalToParent(coupling->GetShaftDirection());
    auto axis_ref=body->GetFrameRefToAbs().TransformDirectionParentToLocal(axis_world);
    w.StartObject();w.Key("name");w.String(body->GetName().c_str());
    w.Key("mass_kg");w.Double(body->GetMass());w.Key("collider_mass_kg");w.Double(volume*800);
    w.Key("body_cog_reference_m");vec(frame.GetPos());w.Key("collider_cog_reference_m");vec(expected_cog);
    w.Key("cog_difference_m");w.Double((frame.GetPos()-expected_cog).Length());
    w.Key("body_inertia_reference_kg_m2");matrix(actual_inertia);
    w.Key("collider_inertia_reference_kg_m2");matrix(expected_inertia);
    w.Key("relative_tensor_difference");w.Double((actual_inertia-expected_inertia).norm()/expected_inertia.norm());
    w.Key("shaft_axis_reference");vec(axis_ref);
    w.Key("shaft_axis_difference");w.Double((axis_ref-ChVector3d(0,-1,0)).Length());
    w.Key("wheel_omega_reference_rad_s");vec(omega);
    w.Key("shaft_omega_rad_s");w.Double(rover.GetDriveshaft(id)->GetPosDt());
    w.EndObject();
  }
  w.EndArray();w.Key("flight_or_soil_validation");w.Bool(false);w.EndObject();output.flush();
  if(!output)throw std::runtime_error("Evidence write failed");
 }catch(const std::exception& error){std::cerr<<"VIPER_FRAME_CHECK_ERROR: "<<error.what()<<'\n';return 1;}
}
