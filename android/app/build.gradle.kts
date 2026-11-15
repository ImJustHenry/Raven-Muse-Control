plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "app.ravenmuse.control"
    compileSdk = 35
    defaultConfig {
        applicationId = "app.ravenmuse.control"
        minSdk = 31
        targetSdk = 35
        versionCode = 4
        versionName = "1.7.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
// QR encoding only (Apache-2.0); no camera, network or analytics.
dependencies {
    implementation("com.google.zxing:core:3.5.3")
    testImplementation("junit:junit:4.13.2")
}
