"""Prepare stored texture sheets for model sampling without changing exports."""


def prepare(image,layout='Auto',colour_key=True):
    from PIL import Image
    import numpy as np
    if layout not in {'Auto','Full image','Main square'}:raise ValueError('Unknown texture layout.')
    # Some 32-bit TGAs declare no alpha attributes: the fourth byte is padding.
    source=(image.convert('RGB') if image.info.get('davilex_tga_alpha_bits')==0 else image).convert('RGBA')
    width,height=source.size
    packed=False;error=None
    # Observed sheets: square base on the left, half-size mip at top right,
    # remaining mips below it. Validate content as well as the 3:2 dimensions.
    if width*2==height*3 and height>=16 and height&(height-1)==0:
        base=source.crop((0,0,height,height))
        half=source.crop((height,0,width,height//2)).convert('RGB')
        reduced=base.convert('RGB').resize(half.size,Image.Resampling.BOX)
        error=float(np.abs(np.array(half,dtype=float)-np.array(reduced,dtype=float)).mean())
        packed=error<=25
    crop=layout=='Main square' or (layout=='Auto' and packed)
    if crop:
        if width<height:raise ValueError('Main square requires an image at least as wide as it is high.')
        source=source.crop((0,0,height,height))
    if colour_key:
        pixels=np.array(source)
        transparent=(pixels[:,:,0]==255)&(pixels[:,:,1]==0)&(pixels[:,:,2]==255)
        pixels[:,:,3][transparent]=0
        source=Image.fromarray(pixels)
    return source,{'stored_size':[width,height],'sampled_size':list(source.size),
                   'packed_mips_detected':packed,'first_mip_mean_error':error,
                   'layout':layout,'colour_key':colour_key}
