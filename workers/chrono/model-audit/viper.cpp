// Execute the unmodified upstream model to inspect its actual mass properties.
// This is an audit, with no calibrated flight-hardware or dynamics claim.
#include <fstream>
#include <iostream>
#include <stdexcept>
#include "chrono/physics/ChSystemSMC.h"
#include "chrono_models/robot/viper/Viper.h"
#include "chrono_thirdparty/rapidjson/prettywriter.h"
#include "chrono_thirdparty/rapidjson/ostreamwrapper.h"

using namespace chrono;
using namespace chrono::viper;

int main(int argc,char** argv) {
    try {
        if(argc!=3) throw std::runtime_error("Usage: clavius_viper_audit chrono-data output.json");
        SetChronoDataPath(std::string(argv[1])+"/");
        ChSystemSMC sys;
        sys.SetNumThreads(1,1,1);
        auto driver=chrono_types::make_shared<ViperSpeedDriver>(1.0,0.0);
        Viper rover(&sys,ViperWheelType::RealWheel);
        rover.SetChassisVisualization(false);
        rover.SetWheelVisualization(false);
        rover.SetSuspensionVisualization(false);
        rover.SetDriver(driver);
        rover.Initialize(ChFrame<>(VNULL,QUNIT));
        std::ofstream output(argv[2]);
        if(!output) throw std::runtime_error("Cannot create audit output");
        rapidjson::OStreamWrapper stream(output);
        rapidjson::PrettyWriter<rapidjson::OStreamWrapper> w(stream);
        auto vector=[&w](const ChVector3d& v) {
            w.StartArray();w.Double(v.x());w.Double(v.y());w.Double(v.z());w.EndArray();
        };
        w.StartObject();
        w.Key("engine_version");w.String(CHRONO_VERSION);
        w.Key("role");w.String("Upstream model instantiation audit; no simulation or flight validation");
        w.Key("upstream_rover_mass_getter_kg");w.Double(rover.GetRoverMass());
        w.Key("bodies");w.StartArray();
        double total=0;
        for(const auto& body:sys.GetBodies()) {
            total+=body->GetMass();
            w.StartObject();
            w.Key("name");w.String(body->GetName().c_str());
            w.Key("mass_kg");w.Double(body->GetMass());
            w.Key("inertia_com_principal_kg_m2");vector(body->GetInertiaXX());
            w.Key("products_of_inertia_kg_m2");vector(body->GetInertiaXY());
            w.Key("com_world_m");vector(body->GetPos());
            auto aux=std::dynamic_pointer_cast<ChBodyAuxRef>(body);
            if(aux) {
                w.Key("reference_world_m");vector(aux->GetFrameRefToAbs().GetPos());
                w.Key("com_relative_reference_m");vector(aux->GetFrameCOMToRef().GetPos());
            }
            w.EndObject();
        }
        w.EndArray();
        w.Key("all_body_mass_kg");w.Double(total);
        w.Key("link_count");w.Uint(static_cast<unsigned>(sys.GetLinks().size()));
        w.Key("shafts");w.StartArray();
        for(int i=0;i<4;i++) {
            auto shaft=rover.GetDriveshaft(static_cast<ViperWheelID>(i));
            w.StartObject();w.Key("inertia_kg_m2");w.Double(shaft->GetInertia());w.EndObject();
        }
        w.EndArray();w.EndObject();
        output.flush();
        if(!output) throw std::runtime_error("Audit write failed");
        std::cout<<"Instantiated original Chrono VIPER model; bodies="<<sys.GetBodies().size()<<" mass_kg="<<total<<'\n';
    } catch(const std::exception& error) {
        std::cerr<<"CLAVIUS_MODEL_AUDIT_ERROR: "<<error.what()<<'\n';
        return 1;
    }
}
