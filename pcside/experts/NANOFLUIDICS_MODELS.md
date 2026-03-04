# NanoFluidics Models (MATLAB -> Python Port Notes)

本目录提供了常见微纳流体实验图像处理算法的 Python 版本，便于将实验室已有 MATLAB 脚本迁移到本系统。

## 已实现模型
1. **接触角估计** (`estimate_contact_angle_from_silhouette`)  
   - MATLAB 常见流程：`rgb2gray -> imgaussfilt -> edge -> bwboundaries`。
2. **粒子速度估计（Lucas-Kanade）** (`estimate_particle_velocity_lk`)  
   - MATLAB 对应：`opticalFlowLK` / `vision.PointTracker`。
3. **弯月面曲率估计** (`estimate_meniscus_curvature`)  
   - MATLAB 对应：边缘提取 + 二次曲线拟合 `polyfit`。

## 集成入口
- `pcside/experts/nanofluidics_models.py`
- `pcside/experts/nanofluidics_multimodel_expert.py`

## 建议扩展
- Young-Laplace 曲线拟合
- 接触线钉扎 (contact line pinning) 统计
- 颗粒浓度场估计（PIV 近似）
- Capillary number / Bond number 在线估计
