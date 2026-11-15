// Independently recompute the original collider's COG before/after its left-side
// mesh transform. This checks model consistency, not measured flight properties.
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include "chrono/geometry/ChTriangleMeshConnected.h"
#include "chrono/core/ChRotation.h"
#include "chrono_thirdparty/rapidjson/ostreamwrapper.h"
#include "chrono_thirdparty/rapidjson/prettywriter.h"

using namespace chrono;

int main(int argc,char** argv) {
    try {
        if(argc!=3) throw std::runtime_error("Usage: clavius_viper_wheel_mass_frames wheel.obj output.json");
        std::ofstream output(argv[2]);
        if(!output) throw std::runtime_error("Cannot create output");
        rapidjson::OStreamWrapper stream(output);
        rapidjson::PrettyWriter<rapidjson::OStreamWrapper> w(stream);
        w.StartObject();
        for(int side=0;side<2;side++) {
            auto mesh=ChTriangleMeshConnected::CreateFromWavefrontFile(argv[1],false,false);
            if(!mesh) throw std::runtime_error("Cannot load original collider");
            const auto rotation=side?QuatFromAngleZ(CH_PI):QUNIT;
            mesh->Transform(VNULL,ChMatrix33<>(rotation));
            mesh->RepairDuplicateVertexes(1e-9);
            double volume;ChVector3d cog;ChMatrix33<> inertia;
            mesh->ComputeMassProperties(true,volume,cog,inertia);
            w.Key(side?"left_rotated_collider":"right_collider");w.StartObject();
            w.Key("assumed_density_kg_m3");w.Double(800);
            w.Key("mass_kg");w.Double(volume*800);
            w.Key("cog_relative_reference_m");w.StartArray();
            w.Double(cog.x());w.Double(cog.y());w.Double(cog.z());w.EndArray();
            w.EndObject();
        }
        w.EndObject();output.flush();
        if(!output) throw std::runtime_error("Output write failed");
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
