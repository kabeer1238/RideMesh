#include "HybridOpusBridge.h"
typedef struct OpusEncoder OpusEncoder;
extern int opus_encoder_ctl(OpusEncoder *, int, ...);
int rm_configure_opus(void *encoder) {
    OpusEncoder *e = (OpusEncoder *)encoder;
    int result = opus_encoder_ctl(e, 4002, 32000); /* bitrate */
    result |= opus_encoder_ctl(e, 4010, 5); /* complexity */
    result |= opus_encoder_ctl(e, 4012, 1); /* in-band FEC */
    result |= opus_encoder_ctl(e, 4014, 10); /* expected packet loss */
    return result;
}
