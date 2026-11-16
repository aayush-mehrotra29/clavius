// Software projection of the flight scene. Reuse its camera, world geometry,
// draw ranges and mapped textures so both renderers follow the same flight.
import * as THREE from 'three';
import {SoftwareGlobe} from './SoftwareGlobe';

export class FlightCanvasRenderer {
  readonly domElement = document.createElement('canvas');
  private readonly ctx: CanvasRenderingContext2D;
  private readonly transform = new THREE.Matrix4();
  private readonly vertex = new THREE.Vector3();
  private readonly globe = new SoftwareGlobe();
  private readonly sunlight = new THREE.Vector3();
  private width = 1;
  private height = 1;
  private ratio = Math.min(devicePixelRatio, 2);

  constructor() {
    // Prefer a CPU-backed surface even when the browser offers a software GPU.
    const ctx = this.domElement.getContext('2d', {willReadFrequently: true});
    if (!ctx) throw new Error('Flight canvas unavailable.');
    this.ctx = ctx;
  }

  setSize(width: number, height: number) {
    this.width = width;
    this.height = height;
    this.domElement.width = Math.round(width * this.ratio);
    this.domElement.height = Math.round(height * this.ratio);
    this.domElement.style.width = width + 'px';
    this.domElement.style.height = height + 'px';
    this.ctx.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
  }

  render(scene: THREE.Scene, camera: THREE.PerspectiveCamera) {
    const {ctx, width, height, vertex, transform} = this;
    const focal = height * camera.projectionMatrix.elements[5] / 2;
    const screenX = (v: THREE.Vector3) => width / 2 - focal * v.x / v.z;
    const screenY = (v: THREE.Vector3) => height / 2 + focal * v.y / v.z;
    scene.updateMatrixWorld();
    camera.updateMatrixWorld();
    ctx.fillStyle = (scene.background as THREE.Color).getStyle();
    ctx.fillRect(0, 0, width, height);

    const bodies: THREE.Mesh[] = [];
    const previous = new THREE.Vector3();
    const clipped = new THREE.Vector3();
    for (const object of scene.children) {
      transform.multiplyMatrices(camera.matrixWorldInverse, object.matrixWorld);
      if (object instanceof THREE.DirectionalLight) this.sunlight.copy(object.position).transformDirection(camera.matrixWorldInverse);
      if (object instanceof THREE.Mesh) {
        bodies.push(object);
        continue;
      }
      if (!(object instanceof THREE.Line || object instanceof THREE.Points)) continue;
      const positions = object.geometry.getAttribute('position');
      const count = Math.min(positions.count, object.geometry.drawRange.count);
      const mat = object.material;
      const segments = object instanceof THREE.LineSegments;
      const stars = object instanceof THREE.Points;
      ctx.strokeStyle = segments ? '#202020' : mat.color.getStyle();
      ctx.fillStyle = mat.color.getStyle();
      ctx.globalAlpha = mat.opacity;
      ctx.lineWidth = mat.linewidth || 1;
      ctx.setLineDash(mat instanceof THREE.LineDashedMaterial ? [5, 4] : []);
      ctx.beginPath();
      for (let i = 0; i < count; i++) {
        vertex.fromBufferAttribute(positions, i).applyMatrix4(transform);
        if (stars) {
          if (vertex.z < -camera.near) ctx.fillRect(screenX(vertex), screenY(vertex), 1.25, 1.25);
        } else if (i > 0 && (!segments || i % 2 === 1)) {
          let a = previous, b = vertex;
          if (a.z <= -camera.near || b.z <= -camera.near) {
            if ((a.z > -camera.near) !== (b.z > -camera.near)) {
              clipped.copy(a).lerp(b, (-camera.near - a.z) / (b.z - a.z));
              if (a.z > -camera.near) a = clipped;
              else b = clipped;
            }
            ctx.moveTo(screenX(a), screenY(a));
            ctx.lineTo(screenX(b), screenY(b));
          }
        }
        previous.copy(vertex);
      }
      if (!stars) ctx.stroke();
    }

    ctx.globalAlpha = 1;
    ctx.setLineDash([]);
    // Depth-sort the planets, then overlay the approach and spacecraft markers.
    const depth = (body: THREE.Mesh) => vertex.copy(body.position).applyMatrix4(camera.matrixWorldInverse).z;
    bodies.sort((a, b) => a.renderOrder - b.renderOrder || depth(a) - depth(b));
    for (const body of bodies) {
      const z = depth(body);
      if (z >= -camera.near) continue;
      const x = screenX(vertex), y = screenY(vertex);
      const mat = body.material;
      const geometry = body.geometry;
      if (geometry instanceof THREE.SphereGeometry) {
        this.globe.draw(ctx, width, height, body, camera, vertex, geometry.parameters.radius, focal, this.sunlight, mat.map?.image);
      } else if (geometry instanceof THREE.RingGeometry || geometry instanceof THREE.OctahedronGeometry) {
        const craft = geometry instanceof THREE.OctahedronGeometry;
        const r = Math.max(3, focal * body.scale.x * (craft ? 4 : geometry.parameters.outerRadius) / -z);
        ctx.strokeStyle = ctx.fillStyle = mat.color.getStyle();
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.stroke();
        if (craft) {
          ctx.beginPath();
          ctx.arc(x, y, r*.45, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
  }
}
